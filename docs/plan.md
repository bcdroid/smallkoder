# Plan: smallkoder v0.1

A command-line coding assistant small enough to read in one sitting: an interactive loop,
one model API, and exactly two tools, `read_file` and `write_file`. Background and sources
are in [research.md](research.md).

## What it looks like

```
$ cd my-project && python -m smallkoder
smallkoder (mimo-v2.6-flash) in /home/me/my-project. Type 'exit' or Ctrl-D to quit.
> read hello.py and add a docstring
  [read_file] hello.py
  [write_file] hello.py wants to change:
  --- hello.py
  +++ hello.py
  @@ -1,2 +1,3 @@
   def greet(name):
  +    """Return a greeting for name."""
       return f"Hello, {name}!"
  Allow this write? [y/N] y
I added a docstring to greet().
> exit
```

## Module layout

Plain Python 3.12, standard library only (pytest for tests).

```
smallkoder/
  __main__.py   # `python -m smallkoder` -> cli.main()
  cli.py        # REPL, approval prompt, reading the API key, --record option
  agent.py      # SYSTEM_PROMPT and run_turn(): the agent loop
  tools.py      # read_file, write_file, their JSON schemas, path checks, run_tool()
  model.py      # Model protocol, OpenCodeModel (real API over urllib), ModelError
  traces.py     # RecordingModel and ReplayModel (save / serve request-response pairs)
scripts/
  record_traces.py   # re-record tests/traces/*.json against the real API
tests/
  fakes.py           # ScriptedModel and fault-injecting fakes
  traces/*.json      # recorded real sessions, committed
  test_*.py
.claude/
  settings.json      # hooks for Claude Code while developing
  hooks/             # run_tests.sh, guard_tests.py
```

Each module has one job, and only `model.py` talks to the network.

## Data shapes

Messages are plain dicts in the OpenAI chat completions format, the same as on the wire,
so there is nothing to translate:

```python
{"role": "system", "content": SYSTEM_PROMPT}
{"role": "user", "content": "read hello.py"}
{"role": "assistant", "content": None,
 "tool_calls": [{"id": "call_1", "type": "function",
                 "function": {"name": "read_file", "arguments": "{\"path\": \"hello.py\"}"}}]}
{"role": "tool", "tool_call_id": "call_1", "content": "def greet(name): ..."}
{"role": "assistant", "content": "It defines greet()."}
```

The model interface is one method:

```python
class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return the assistant message: {"role", "content", and maybe "tool_calls"}."""
```

`OpenCodeModel.complete` keeps only `role`, `content` and `tool_calls` (with `id`, `type`,
`function.name`, `function.arguments`) and drops extras like `reasoning`. That keeps
messages and traces small and provider-neutral. It raises `ModelError` for any failure.

Tool schemas (`TOOLS` in `tools.py`) are written to satisfy OpenAI strict-mode rules
(`additionalProperties: false`, every field required), though we do not rely on the
server enforcing them.

## The loop (`agent.run_turn`)

```python
def run_turn(model, messages, approve, root, max_steps=20) -> str:
    for _ in range(max_steps):
        reply = model.complete(messages, TOOLS)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return reply.get("content") or ""
        for call in reply["tool_calls"]:
            result = run_tool(call["function"]["name"], call["function"]["arguments"], root, approve)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return "(stopped: too many steps without a final answer)"
```

`messages` is the whole conversation and lives in the CLI between turns. `run_turn`
appends to it.

**How it ends.** One turn ends when the model replies without tool calls, or after
`max_steps` model calls (a safety stop against loops). The session ends when the user
types `exit` or `quit`, or presses Ctrl-D (EOF) or Ctrl-C.

## Tools and their guardrails (`tools.py`)

- `read_file(path)` returns the file's text.
- `write_file(path, content)` replaces the whole file (creating parent directories) and
  returns `"Wrote N lines to path"`.

Both go through `resolve_path(root, path)`: `(root / path).resolve()` must satisfy
`.is_relative_to(root)`, which catches `../`, absolute paths and symlinks pointing out.
Files named `.env` are also refused, so the agent can't send our API key to the model.

**Approval.** `write_file` calls `approve(path, old_text, new_text) -> bool` before
writing. The CLI's approver prints a unified diff (`difflib`) and asks `Allow this write?
[y/N]`. Anything other than `y`/`yes` means no. Tests pass simple lambdas. A declined
write returns an error result so the model knows.

## Error handling

The rule: **a tool problem is never a crash; it becomes an `Error: ...` tool result** the
model can read and react to (as in pi and nanocode). `run_tool` produces these:

| Problem | Tool result |
|---|---|
| Unknown tool name | `Error: unknown tool 'x'. Available tools: read_file, write_file` |
| Arguments not valid JSON, or not an object | `Error: arguments must be a JSON object: ...` |
| Missing, extra or non-string argument | `Error: read_file needs a string argument 'path'` etc. |
| Path outside the working directory | `Error: path 'x' is outside the working directory` |
| `.env` file | `Error: refusing to touch secret file '.env'` |
| Missing file / is a directory / not UTF-8 | `Error: file not found: x` etc. |
| User declined | `Error: the user declined this write` |

**API errors** (HTTP error status, network failure, timeout, malformed JSON response)
are different: the model can't fix them. `OpenCodeModel` raises `ModelError`, the CLI
prints it, rolls the conversation back to before the user's message, and waits for the
next input. The error text never includes the key.

## The API key

`cli.py` reads `OPENCODE_GO` from the environment, falling back to a `.env` file in the
current directory. The key only goes into the `Authorization` header inside
`OpenCodeModel`; it is never printed, and traces never see it because `complete()` only
receives messages and tools.

## Test strategy

**`pytest` is offline, keyless and deterministic.** A `conftest.py` fixture blocks socket
connections in every test not marked `live`, so an accidental network call fails loudly.

| Layer | How it's tested |
|---|---|
| `tools.py` | Directly, in `tmp_path` workspaces: reads, writes, refusals, every error row above, symlink escape. |
| `agent.py` | **Scripted fake** (`tests/fakes.py`): `ScriptedModel([reply1, reply2, ...])` returns replies in order and records what it was sent. E.g. "first a `read_file` call, then a final answer". |
| Error handling | **Fault-injection fakes**: replies with invalid JSON arguments, unknown tools, missing arguments, many calls in one reply, endless tool calls (step limit). |
| `model.py` | `OpenCodeModel` takes an injectable `post` function; tests check the URL, headers, body and response parsing, and HTTP-error handling, with no network. |
| `traces.py` | `RecordingModel` wraps a fake and writes JSON; `ReplayModel` returns recorded replies and raises `TraceMismatch` if a request differs. A test checks that no trace contains a key or an auth header. |
| End to end | **Recorded real sessions** in `tests/traces/*.json`, replayed through the real `run_turn` and tools. Each trace stores the starting files, the user prompts, the approval answers, every request/response pair, and the final files. |
| `cli.py` | `main()` takes injectable `input`/`print` functions and a model: exit, EOF, approval y/n, API-error recovery. |
| Real API | `tests/test_live.py`, marked `live`, skipped unless `SMALLKODER_LIVE=1`. |

Replay checks requests exactly. So changing the system prompt or a tool description makes
the trace tests fail until traces are re-recorded with `python scripts/record_traces.py`.
That is deliberate: those changes alter what the model sees.

## Development guardrails (Claude Code)

- **pytest after every edit:** a `PostToolUse` hook on `Edit|Write` runs the suite and
  exits 2 with the failure summary, so failures are shown to Claude straight away.
- **No weakening tests:** a `PreToolUse` hook on `Edit|Write` for files under `tests/`
  blocks (exit 2) any skip or xfail marker, and any edit that removes an existing
  `assert` line unless the new text carries a `# assertion-changed: <reason>` comment.
  The change can still be made, but only visibly, with a reason that shows in the diff.
- The hook scripts have their own tests.

## Order of work (TDD)

1. Project setup: `pyproject.toml`, conftest network block, hooks, README stub, backlog.
2. `resolve_path` → `read_file` → `write_file` + approval → `run_tool` validation.
3. `ScriptedModel`, then `run_turn`: final answer, tool round trip, multiple calls, step limit, faults.
4. `OpenCodeModel` with an injected `post`.
5. `RecordingModel` / `ReplayModel`.
6. `cli.main`.
7. Record real traces, then add replay tests.
8. Live test, README.

Each behaviour gets a red commit (`test: ... (red)`) and a green commit (`feat: ... (green)`).

## Out of scope for v0.1

Everything in [backlog.md](backlog.md): editing tools, bash, streaming, history limits,
and the rest.
