# 0003. Approval is the only guardrail for commands; the key is hidden from their environment

- **Status:** Accepted (decided by the user, 2026-11-09; recorded 2026-11-11)
- **Date:** 2026-11-09
- **Spec:** [docs/specs/run-command.md](../specs/run-command.md)

## Context

The README advertises two guardrails enforced in code: file paths stay inside the
working directory (`resolve_path`), and `.env` is refused, so the model can't send our
API key to the API. Both live in the file tools. A shell command gets around both:
`cat ../secret.txt`, `cat .env`, `echo $OPENCODE_GO`.

## Decision

- Approval ([ADR 0002](0002-approve-every-command.md)) is the only guardrail on what a
  command does. The command text is not checked.
- What code *can* guarantee, it does: `OPENCODE_GO` is removed from the command's
  environment, so `echo $OPENCODE_GO` prints nothing.
- The README says plainly that the path and `.env` guardrails cover `read_file` and
  `write_file` only, with examples of what a yes to a command can do.

## Alternatives considered

- **Also refuse commands whose text mentions `.env`.** It catches the obvious case and
  nothing else: `cat .e*`, `cat $(printf '.%s' env)`, `python3 -c ...`, or a script the
  model wrote a moment ago. A check that looks like a guarantee but isn't one is worse
  than none, because it invites trust. (Worth building one day as a lesson in why
  deny-lists fail.)
- **Sandbox commands** (bubblewrap with the project mounted and `.env` hidden, or a
  container). That would be a real guarantee, but it works only on Linux, needs `bwrap`
  installed, and adds a lot of code to a project meant to be read in class. Kept in the
  backlog as "Sandboxing commands".

## Consequences

- The user is the guardrail for commands, and must read each one. The README says so.
- The `.env` file on disk is still readable by an approved command; only the variable is
  hidden.
- The difference between "the user was asked" and "the command was contained" is now a
  documented teaching point.
