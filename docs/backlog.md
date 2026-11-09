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

## Configuration and modes

- **System-prompt / AGENTS.md instruction file.** Load `AGENTS.md` from the working
  directory into the system prompt, as pi and Claude Code do with `AGENTS.md` and
  `CLAUDE.md`. *Teaches:* how project conventions reach the model; prompt injection
  risk from files you didn't write.
- **Non-interactive mode (`-p "prompt"`).** Run one turn and exit, for scripts and CI.
  Needs a policy for approvals (deny all writes, or `--yes`). *Teaches:* argparse, exit
  codes, and that unattended agents need stricter guardrails.
- **Sessions saved to disk.** Save `messages` as JSON after each turn and offer
  `--resume`. The trace format is already most of the way there. *Teaches:*
  serialisation and why a plain-dict message format pays off.
- **Model choice and other providers.** `--model` flag; an Anthropic-messages adapter
  behind the same `Model` interface. *Teaches:* the value of the one-method interface.

## Bigger ideas

- **Subagents.** A tool that starts a fresh `run_turn` with its own short history to do
  a side task (for example "find where X is defined") and returns only the summary.
  *Teaches:* recursion, context isolation, and why it saves tokens.

## Found while building

- **Truncated replies.** When `finish_reason` is `"length"`, tool-call arguments may be
  cut off. pi fails those calls rather than running them. We currently rely on the JSON
  parse failing. *Teaches:* reading `finish_reason`, defensive handling.
- **Large files.** `read_file` returns the whole file. Add a size limit, or
  `offset`/`limit` arguments like pi's `read`. *Teaches:* context budgets.
- **Symlink race (TOCTOU).** The path check and the write are separate steps, so a
  symlink swapped in between could escape. Fine for teaching; a real tool would open
  with `O_NOFOLLOW` or run in a sandbox. *Teaches:* time-of-check vs time-of-use.
