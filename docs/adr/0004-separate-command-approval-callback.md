# 0004. A separate `approve_command` callback that declines by default

- **Status:** Accepted
- **Date:** 2026-11-09
- **Spec:** [docs/specs/run-command.md](../specs/run-command.md)

## Context

Writes are approved through `approve(path, old_text, new_text) -> bool`, passed down
from the CLI through `run_turn` and `run_tool`. Commands need approval too, but the
question is different: there is no path and no diff, only a command string. About 30
call sites (tests, the trace recorder and replay, the live test) already pass `approve`
positionally.

## Decision

Add a second callback, `approve_command(command) -> bool`. `run_tool` and `run_turn` take
it as a keyword argument, and it defaults to `never`, which always returns `False`. The
CLI passes a real one. The trace recorder and replay pass the same function as both
`approve` and `approve_command`, so a trace's `approvals` list holds every answer in the
order it was asked.

## Alternatives considered

- **One generalised approver** taking a request object (`WriteRequest | CommandRequest`).
  One parameter instead of two, but every existing approver and call site would have to
  change, and each approver would have to branch on the request type.
- **Reuse `approve` with a different argument shape** (`approve(command)`). Approvers
  would have to guess what they were asked from the number of arguments.
- **Make `approve_command` required.** Every caller would have to decide explicitly, but
  every existing call would break, for no safety gain over a default of "no".

## Consequences

- Existing callers are unchanged. Code that forgets to pass an approver gets every
  command declined: the safe failure.
- `run_turn` now has two approval keywords. A third kind of approval (for example plan
  approval) would be a good time to revisit the single-approver design.
