# Backlog

Future work for smallkoder, roughly in teaching order. This is a living list: add to it
whenever something comes up while building. Each item says why it is interesting and
what it would teach.

## Tools

- **File editing tool (search/replace or apply a patch).** `write_file` resends the whole
  file, which is slow and expensive for big files, and models make mistakes copying long
  text. An `edit_file(path, old, new)` that requires `old` to appear exactly once is what
  pi, Claude Code and "How to Build an Agent" use. *Teaches:* designing a tool that is
  hard to misuse, and useful error messages ("old text found 3 times") that let the
  model fix its own call.
- **Bash / run-command tool with a permission prompt.** The single most powerful tool:
  run tests, git, linters. mini-swe-agent shows bash alone is enough. *Teaches:*
  `subprocess`, timeouts, output truncation, and why command approval is harder than
  file approval (`rm -rf` hidden inside a script; allow-lists vs deny-lists).
- **Listing and searching files** (`list_files`, `glob`, `grep`). Today the model must
  guess file names. *Teaches:* `pathlib.glob`, ignoring `.git` and `.venv`, limiting
  output size so one call can't flood the context.

## The conversation

- **Streaming output.** Print tokens as they arrive (`"stream": true`, server-sent
  events) instead of waiting for the whole reply. *Teaches:* SSE parsing, and assembling
  tool-call arguments that arrive in fragments.
- **Conversation history management and token counting.** `messages` grows forever and
  will eventually exceed the model's context window. Track `usage.prompt_tokens` from
  each response and warn near the limit. *Teaches:* what a context window is and why
  long sessions get slow and expensive.
- **Compaction.** When history gets long, ask the model to summarise older turns and
  replace them with the summary. *Teaches:* trading detail for space; what an agent
  "remembers".
- **Cost display.** OpenCode Go returns token counts and a cost estimate in `usage`;
  show it after each turn and for the session. *Teaches:* reading API metadata; that
  every loop iteration costs money (resending the whole history each time).

## Commands and display

- **A `/help` command, and slash commands in general.** Today the only command is
  `exit`/`quit`, and every other line goes to the model. A small dispatch table (`/help`,
  `/model`, `/context`, `/cost`, ...) checked before `run_turn` lets the user talk to
  smallkoder instead of the model. `/help` should be generated from that table so it
  can't go stale. *Teaches:* dispatch tables; separating the program's commands from the
  conversation; deciding what a `/typo` does (an error, or sent to the model?).
- **Show every message to and from the model (`--verbose` or `/verbose`).** Print the
  full request (system prompt, history, tool results) and reply, optionally with the
  model's reasoning. OpenCode Go does return a `reasoning` field, but `clean_reply`
  (`smallkoder/model.py:84`) drops it so it is never sent back. Keep it for display
  only, still out of `messages`. Not every model returns reasoning, and field names vary
  (`reasoning`, `reasoning_content`; see research.md). *Teaches:* that "the conversation"
  is just a list of dicts resent each time; how much hidden text a reply costs.
- **`/context` and `/cost` commands.** Show how full the context window is and what the
  session has cost so far. They build on the token-counting and cost-display items
  above: those collect the numbers, these display them on request. *Teaches:* the same
  as those items, made visible at the moment the user wonders about it.
- **Attach files with `@filename`.** Not implemented yet. Expand `@path` in the user's
  line into the file's contents before sending, so the model needn't call `read_file`.
  It must go through the same `resolve_path` checks as the tools (stay in the project,
  refuse `.env`). Otherwise `@../secrets` or `@.env` would get around the guardrails.
  Needs rules for email addresses, `@` in code, and missing files. *Teaches:* reusing one
  checked path for every way into the filesystem; that user input can leak secrets too.

## Configuration and modes

- **System-prompt / AGENTS.md instruction file.** Load `AGENTS.md` from the working
  directory into the system prompt, as pi and Claude Code do with `AGENTS.md` and
  `CLAUDE.md`. *Teaches:* how project conventions reach the model; prompt injection
  risk from files you didn't write.
- **System prompt in its own file.** Move `SYSTEM_PROMPT` out of `smallkoder/agent.py`
  into a text file in the package (for example `smallkoder/system_prompt.md`, loaded with
  `importlib.resources`) so it can be read and edited without touching code. It pairs
  with the `AGENTS.md` item: a built-in base prompt plus project additions. Any edit
  still changes what is sent, so the recorded traces must be re-recorded, and the
  "no `/` in the prompt" test still applies. *Teaches:* package data; that a prompt is
  configuration, but configuration the tests depend on.
- **Non-interactive mode (`-p "prompt"`).** Run one turn and exit, for scripts and CI.
  Needs a policy for approvals (deny all writes, or `--yes`). *Teaches:* argparse, exit
  codes, and that unattended agents need stricter guardrails.
- **Sessions saved to disk.** Save `messages` as JSON after each turn and offer
  `--resume`. The trace format is already most of the way there. *Teaches:*
  serialisation and why a plain-dict message format pays off.
- **Readable transcripts.** Different from saved sessions: a Markdown (or JSON Lines)
  log of everything that happened, for people to read rather than to resume. It covers
  user lines, replies, tool calls and results, approvals and declines, and optionally
  reasoning and token usage. `RecordingModel` in `smallkoder/traces.py` already captures
  every request and response, but only in tests. *Teaches:* the difference between state
  (enough to continue) and a log (enough to understand what happened); keeping secrets
  out of logs.
- **Model choice and other providers.** `--model` already picks the model at start-up.
  Still to do: a `/model` command to list models and switch mid-session (the history
  carries over; a new `OpenCodeModel` means a new session id), a default model in a
  config file, and an Anthropic-messages adapter behind the same `Model` interface.
  *Teaches:* the value of the one-method interface; that history written for one model
  usually works with another.

## Bigger ideas

- **Subagents.** A tool that starts a fresh `run_turn` with its own short history to do
  a side task (for example "find where X is defined") and returns only the summary.
  *Teaches:* recursion, context isolation, and why it saves tokens.
- **A TUI (full-screen terminal interface).** A scrolling conversation pane, an input
  line with history and editing, a status bar (model, context use, cost), and diffs shown
  in a pane for approval. The standard library has `curses` (not on Windows) and
  `readline`. A library like Textual is far easier; it would be the first runtime
  dependency (`uv add textual`). Keep `run_turn` unchanged; the TUI is just another
  `input`/`output`/`approve`. *Teaches:* event loops; why the agent loop was kept free
  of printing; the cost of a dependency.

## Developer guardrails

These are about the repo and the agent editing it, not smallkoder itself.

- **Ruff and mypy.** Neither is set up. Add them with `uv add --dev ruff mypy`,
  configure them in `pyproject.toml`, and run them from the `PostToolUse` hook next to
  pytest. Type hints are only partial today, so start mypy non-strict and tighten it
  later. Ruff can also format the code, though that would mean one large diff first.
  *Teaches:* static checks catch different bugs than tests do (wrong types, unused
  names, unreachable code); a check matters most when it runs automatically.
- **A Stop hook.** Today the tests run after each edit, but nothing checks the state
  when Claude says it is done. A `Stop` hook could run the full suite (plus ruff and
  mypy) and exit 2 to keep Claude working while anything fails. It must check
  `stop_hook_active` so it can't loop forever, and it needs an answer for the TDD red
  step, where a failing test is the point. *Teaches:* hook events (per edit vs. end of
  turn); "done" as something checked rather than claimed.
- **A `Read(./.env)` deny rule.** `.claude/settings.json` has no `permissions` block, so
  nothing stops Claude Code itself from reading the API key; `CLAUDE.md` only asks. Add
  `"permissions": {"deny": ["Read(./.env)", "Edit(./.env)"]}`. A Read rule does not cover
  `cat .env` run through Bash (see research.md), so this pairs with the "Hooks don't
  see Bash edits" item below. Running `uv run smallkoder` still works, because the
  program reads `.env` itself. *Teaches:* the README's own rule ("a prompt is a request,
  code is a guarantee") applied to the developer's agent; the limits of path-based rules.
- **A test that fails if a trace contains the real key.** Partly done:
  `test_trace_has_no_secrets` checks every trace for known patterns (`oc_sk`, `sk-`,
  `Bearer`, header names), and `test_traces.py` checks that a fake key is never
  recorded. Neither compares against the actual key, so a key in an unexpected format
  would slip through. Add an exact-value check: `scripts/record_traces.py` refuses to
  save a trace containing the key it used, and a test checks it when a key is
  available. The default run must stay keyless. *Teaches:* pattern checks vs.
  exact-value checks; checking at the moment of writing, not only afterwards.

## Found while building

- **Truncated replies.** When `finish_reason` is `"length"`, tool-call arguments may be
  cut off. pi fails those calls rather than running them. We currently rely on the JSON
  parse failing. *Teaches:* reading `finish_reason`, defensive handling.
- **Large files.** `read_file` returns the whole file. Add a size limit, or
  `offset`/`limit` arguments like pi's `read`. *Teaches:* context budgets.
- **Other secret files.** Only files named exactly `.env` are refused; `.env.local`,
  `id_rsa`, `credentials.json` are not. A small deny-list (or glob patterns) would be
  better. *Teaches:* deny-lists are never complete, which is why real tools also sandbox.
- **Ctrl-C cancels the turn, not the program.** Today Ctrl-C during a model call quits
  smallkoder. Claude Code cancels the current turn and keeps the conversation.
  *Teaches:* signal handling and rolling back a half-finished turn.
- **Large writes and diffs.** The approval prompt prints the whole diff; a rewrite of a
  1000-line file is unreadable. Page it, or summarise (+12 −3 lines) with an option to
  see it all. *Teaches:* UX of approval prompts; why edit tools beat whole-file writes.
- **Hooks don't see Bash edits.** The Claude Code test guard only inspects `Edit` and
  `Write`. A `PreToolUse` hook on `Bash` that refuses commands touching `tests/`, or a
  git pre-commit hook running the same checks on the staged diff, would close the gap.
  *Teaches:* defence in depth; where in the workflow a check belongs.
- **Symlink race (TOCTOU).** The path check and the write are separate steps, so a
  symlink swapped in between could escape. Fine for teaching; a real tool would open
  with `O_NOFOLLOW` or run in a sandbox. *Teaches:* time-of-check vs time-of-use.
