# Research: how small coding agents are built

Research for `smallkoder` (see [brief.md](brief.md)). Gathered 2026-11-09. Line numbers in
pi links are pinned to commit `5c37d3b`; they will drift on `main`.

## 1. The API we will use: OpenCode Go

- **Endpoint:** `POST https://opencode.ai/inference/go/openai/v1/chat/completions`
  (Go base URL `https://opencode.ai/inference/go` plus the OpenAI path). Sources:
  <https://opencode.ai/v2/docs/console/go>, <https://opencode.ai/v2/docs/console/harnesses>.
- **Auth:** `Authorization: Bearer <key>` (<https://opencode.ai/v2/docs/console/api>).
- **Session header is required.** Without `x-opencode-session: ses_...` the server
  answers `400 MissingSessionID` (observed). Clients should also send their own
  `User-Agent` (Go docs).
- **Model:** `mimo-v2.6-flash`, the cheapest paid model on the chat completions path
  ($0.14 in / $0.28 out per million tokens). Some models use other paths
  (`/anthropic/v1/messages`, `/openai/v1/responses`); we stick to chat completions.
- **Observed behaviour** (our own probes, 2026-11-09):
  - A 5-token request returned HTTP 200 with `content: null` and `finish_reason:
    "length"`: the model spent 4 tokens on hidden reasoning. **Use a generous
    `max_tokens`.**
  - With a `read_file` tool, the model answered `finish_reason: "tool_calls"` in the
    standard OpenAI shape (below), plus extra non-standard fields `reasoning` and
    `reasoning_details`, which we can ignore.
  - Some third-party pages still give an old base URL, `https://opencode.ai/zen/go/v1`;
    the official docs above use `/inference/go`.

## 2. The wire format: OpenAI chat completions tool calling

From the API reference
(<https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create>)
and the function calling guide (<https://developers.openai.com/api/docs/guides/function-calling>):

- **Tools** are sent as a list of JSON Schemas:
  `{"type": "function", "function": {"name", "description", "parameters": <JSON Schema>}}`.
- **The assistant asks for tools** with a message like:
  ```json
  {"role": "assistant", "content": null,
   "tool_calls": [{"id": "call_2b4e...", "type": "function",
                   "function": {"name": "read_file", "arguments": "{\"path\": \"hello.py\"}"}}]}
  ```
  `arguments` is a **JSON string**, not an object. The model writes it, so it can be
  invalid JSON or have the wrong fields. We have to parse and check it ourselves.
- **We answer each call** with one message per `id`:
  `{"role": "tool", "tool_call_id": "call_2b4e...", "content": "...file text..."}`.
- **`finish_reason`** is `"tool_calls"`, `"stop"`, `"length"` or `"content_filter"`.
- **Parallel tool calls** are on by default: one assistant message may hold several
  calls, and every one needs its own `tool` reply.
- Chat completions has no "this tool result is an error" flag (Anthropic's API has
  `is_error`), so an error is just text in `content`. pi does the same for this API
  ([`openai-completions.ts#L1418-L1427`](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/ai/src/api/openai-completions.ts#L1418-L1427)).

## 3. The agent loop

Every source describes the same loop. Anthropic's "Building effective agents" puts it as
agents being "typically just LLMs using tools based on environmental feedback in a loop"
(<https://www.anthropic.com/engineering/building-effective-agents>). Thorsten Ball's
"How to Build an Agent" (<https://ampcode.com/how-to-build-an-agent>) says it takes
"an LLM, a loop, and enough tokens".

```
messages = [system prompt]
forever:
    messages += user input
    loop:
        reply = model(messages, tools)
        messages += reply
        if reply has no tool calls: show reply, break
        for each call: messages += tool result (or error text)
```

What the real examples do:

| Agent | Size / language | Tools | Tool errors | Permission prompts |
|---|---|---|---|---|
| **pi** ([repo](https://github.com/earendil-works/pi), [blog](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/)) | TypeScript monorepo: `pi-ai` (LLM APIs), `pi-agent-core` (loop), `pi-tui`, `pi-coding-agent` ([README#L76-L84](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/README.md#L76-L84)) | read, bash, edit, write ([settings-manager.ts#L85](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/coding-agent/src/core/settings-manager.ts#L85)) | Returned to the model as error tool results; "Never rejects for tool failures" ([agent-loop.ts#L718-L862](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/agent/src/agent-loop.ts#L718-L862)) | None, on purpose ("YOLO by default"); optional hook extension |
| **How to Build an Agent** ([article](https://ampcode.com/how-to-build-an-agent)) | Go, ~300-400 lines | read_file, list_files, edit_file | Returned as error tool results | None |
| **nanocode** ([repo](https://github.com/1rgs/nanocode)) | One Python file, ~270 lines, `urllib` only | read, write, edit, glob, grep, bash | `try/except` → `"error: ..."` string | None, no path checks |
| **mini-swe-agent** ([repo](https://github.com/SWE-agent/mini-swe-agent)) | Python, ~100-200 line agent class | bash only | Format errors fed back as messages; gives up after 3 in a row | `confirm` mode (default) asks before non-whitelisted commands; also `yolo` |

Details worth copying:

- **pi's loop** ([`runLoop`, agent-loop.ts#L172-L330](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/agent/src/agent-loop.ts#L172-L330))
  keeps going while the last reply had tool calls. Unknown tools, bad arguments and
  exceptions all turn into error results, so the model can see its mistake and retry.
  If a reply was cut off (`stopReason === "length"`) its tool calls are failed rather than
  run, because the arguments may be truncated (L273-L279).
- **Stopping conditions:** Anthropic recommends "stopping conditions (such as a maximum
  number of iterations)". mini-swe-agent has step, cost and time limits.
- **Validation:** pi validates arguments against the schema and sends back messages like
  `Validation failed for tool "X": ...` listing the bad fields
  ([validation.ts#L54-L69](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/ai/src/utils/validation.ts#L54-L69)).
- **Provider quirks are real:** pi's chat completions adapter handles several names for
  reasoning text (`reasoning_content`, `reasoning`, `reasoning_text`), `max_tokens` vs
  `max_completion_tokens`, and tool call id formats
  ([openai-completions.ts#L578-L605](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/ai/src/api/openai-completions.ts#L578-L605)).
  We saw the `reasoning` field from OpenCode Go ourselves.

## 4. Tool definitions

- pi writes schemas with TypeBox; they compile to plain JSON Schema. Its `write` tool is
  just `{path: string, content: string}`
  ([write.ts#L10-L13](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/coding-agent/src/core/tools/write.ts#L10-L13)),
  the same as our planned `write_file`.
- OpenAI's optional `strict` mode needs `additionalProperties: false` and every property
  `required`; chat completions is non-strict by default (function calling guide). We
  will write schemas that satisfy strict rules anyway, but still check arguments
  ourselves because the server may not enforce them.
- Anthropic's article advises spending effort on the "agent-computer interface":
  clear names, clear descriptions, and tools that are hard to misuse.

## 5. System prompts

- pi's default preamble is one sentence: "You are a coding assistant running inside pi,
  a coding agent harness. Help users inspect files, run commands, and modify code."
  It then adds one line per tool, a few rules ("Be concise in your responses"), project
  context and the working directory
  ([system-prompt.ts#L88-L182](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/coding-agent/src/core/system-prompt.ts#L88-L182)).
  The blog says prompt plus tool definitions come to under 1000 tokens.
- pi loads `AGENTS.md` / `CLAUDE.md` from the working directory and its parents and wraps
  each in `<project_instructions>`
  ([resource-loader.ts#L212-L300](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/packages/coding-agent/src/core/resource-loader.ts#L212-L300)).
  That goes in the backlog.

## 6. Permission prompts

- **pi: none.** "Pi does not include a built-in permission system"; it recommends
  containers instead ([README#L88-L96](https://github.com/earendil-works/pi/blob/5c37d3be1c3c62c113b52780cc1cbac77ba5a69f/README.md#L88-L96)).
  The blog's argument: everyone ends up in "YOLO mode" anyway.
- **Claude Code** asks before file edits in its default mode, and has allow/ask/deny
  rules: "Rules are evaluated in order: deny, then ask, then allow" and "Permission
  rules are enforced by Claude Code, not by the model"
  (<https://code.claude.com/docs/en/permissions>, <https://code.claude.com/docs/en/permission-modes>).
- **Codex CLI** combines a sandbox (`read-only`, `workspace-write`, `danger-full-access`)
  with an approval policy (<https://learn.chatgpt.com/docs/agent-approvals-security>).
- **Aider** relies on git: it commits every edit and offers `/undo`
  (<https://aider.chat/docs/git.html>).
- **mini-swe-agent** asks before commands unless they match a whitelist.

The key lesson from Claude Code: **the check has to be in our code, not in the prompt.**
Telling the model "don't write outside this folder" is a request; refusing the write in
`write_file` is a guarantee.

## 7. Confining paths to the working directory

From the `pathlib` docs (<https://docs.python.org/3/library/pathlib.html>):
`is_relative_to` "is string-based; it neither accesses the filesystem nor treats '..'
segments specially", so it is only safe on a path that has gone through `resolve()`,
which removes `..` and follows symlinks:

```python
root = Path.cwd().resolve()
target = (root / user_path).resolve()
if not target.is_relative_to(root):
    raise ToolError("path is outside the working directory")
```

`root / "/etc/passwd"` is `/etc/passwd`, so absolute paths are caught too. One gap
remains: a symlink created between the check and the write (a "TOCTOU" race). That is
fine for a teaching tool, but worth knowing about.

## 8. Claude Code hooks (for the guardrails around *us* while building)

From <https://code.claude.com/docs/en/hooks>:

- Hooks live in `.claude/settings.json` under `hooks.<Event>[].{matcher, hooks[]}`.
  `"matcher": "Edit|Write"` matches exactly those two tools.
- The hook gets JSON on stdin: `tool_name`, `tool_input` (for Write: `file_path`,
  `content`; for Edit: `file_path`, `old_string`, `new_string`, `replace_all`), `cwd`.
- **Exit code 2** is the important one. On `PreToolUse` it blocks the tool call and shows
  stderr to Claude. On `PostToolUse` the tool has already run, and stderr is shown to
  Claude. Exit code 1 is a non-blocking error the model does not see, so it is useless
  for enforcing anything.
- Caveat: hooks on `Edit|Write` do not fire when a file is changed through Bash, and
  permission deny rules like `Edit(tests/**)` do not cover subprocesses. These
  guardrails catch mistakes; they are not a security boundary.

## 9. Further details (not needed for v0.1, but worth knowing)

**OpenCode Go models and prices** (<https://opencode.ai/v2/docs/console/go>, 2026-11-09;
the docs say limits may change; check `https://opencode.ai/inference/go/v1/models` for the
live list). Cheapest models on the chat completions path, USD per million tokens:

| Model id | Input | Output |
|---|---|---|
| `mimo-v2.6-flash` (our default) | $0.14 | $0.28 |
| `mimo-v2.5` | $0.14 | $0.28 |
| `hy3` | $0.14 | $0.58 |
| `glm-5.3-flash` | $0.15 | $0.50 |
| `minimax-m3.1-flash` | $0.15 | $0.60 |
| `kimi-k2.7-code` | $0.95 | $4.00 |

- Other models use other paths: `qwen3.7-plus`, `qwen3.8-*`, `claude-haiku-5-5` and
  `minimax-m3` are on `/anthropic/v1/messages`; `gpt-*`, `grok-4.7` and `muse-spark-*`
  are on `/openai/v1/responses`. The docs say Console translates between APIs, but we
  only tested chat completions.
- Usage limits per model: 20% of the monthly allowance per 5 hours, 50% per week.
- The "Free" models (e.g. `beam-free`) only work from inside OpenCode itself; other
  clients get HTTP 403 even with a valid key.
- The docs show keys starting `oc_sk_`.

**Minimal agents:**

- **mini-swe-agent**: the README says it "doesn't even need to use the tool-calling
  interface" (a regex pulls a bash block out of plain text), but the current default
  model class sends `tools=[BASH_TOOL]` and uses native tool calling. The text-based
  version is now a separate option. Lesson: check the code, not just the README.
- **"How to Build an Agent"** gives several sizes for the same program ("less than 400
  lines", ~190 midway, "300 lines" at the end), depending on what is counted.
- **pi's blog post is partly out of date:** it says validation uses TypeBox + AJV, and
  that thinking from another model becomes `<thinking>` text. The current code uses its
  own `pi-schema` package and drops foreign thinking blocks instead.

**Permissions elsewhere:**

- **Codex CLI** has removed the `untrusted` approval policy (older blogs still list it,
  along with `--full-auto`). The "Auto" preset is
  `--sandbox workspace-write --ask-for-approval on-request`.
- **Aider** has `--auto-test` and `--test-cmd` to run tests after each change, the same
  idea as our PostToolUse hook, but built into the tool (<https://aider.chat/docs/config/options.html>).

**Claude Code hooks, finer points** (<https://code.claude.com/docs/en/hooks>):

- A matcher made only of names and `|` matches exactly; anything else is an unanchored
  regex, so `Edit.*` also matches `NotebookEdit`. Use `^...$` for exact regexes.
- Instead of exit code 2, a hook can exit 0 and print JSON. PostToolUse supports
  `{"decision": "block", "reason": ...}`, and PreToolUse supports
  `hookSpecificOutput.permissionDecision` (`allow` / `deny` / `ask`). We used exit
  codes because they are easier to read.
- Deny rules use gitignore-style paths, and `Edit(...)` rules cover every built-in
  file-editing tool (write `Edit(docs/**)`, not `Write(docs/**)`).

## What this means for smallkoder

1. **Use the plain chat completions format** with `urllib`, like nanocode. No SDK, so
   students can see every byte that goes over the wire. Send `x-opencode-session` and a
   real `max_tokens`.
2. **The loop is ~20 lines.** Keep calling the model until a reply has no tool calls, and
   add a step limit as a safety stop.
3. **Never crash on a bad tool call.** Unknown tool, invalid JSON, missing or wrong
   arguments, missing file, refused path, declined write: each becomes an `Error: ...`
   tool result the model can read and react to (pi's approach).
4. **Unlike pi, ask before every write.** The program is for learning, and the
   permission prompt is the guardrail students should see. Show a diff so the user knows
   what they are approving.
5. **Enforce the path check in code**, with `resolve()` + `is_relative_to()`.
6. **Keep the system prompt short** (pi shows a few sentences are enough), and keep the
   working directory's absolute path out of it so recorded traces replay anywhere.
7. **Put the model behind one method**, `complete(messages, tools)`, so tests can swap
   in scripted fakes and recorded traces. This also mirrors pi's split between the LLM
   layer (`pi-ai`) and the loop (`pi-agent-core`).
8. **Guardrails for the developer** (Claude Code, while building this): a `PostToolUse`
   hook that runs pytest and exits 2 on failure, and a `PreToolUse` hook that exits 2 to
   block skipped or weakened tests.
