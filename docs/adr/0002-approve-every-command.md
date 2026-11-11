# 0002. `run_command` asks about every command

- **Status:** Accepted (decided by the user, 2026-11-09; recorded 2026-11-11)
- **Date:** 2026-11-09
- **Spec:** [docs/specs/run-command.md](../specs/run-command.md)

## Context

A shell command can do anything the user can. smallkoder already asks before every
write, showing a diff. Commands need some approval policy too, and the backlog item
names the tension: "why command approval is harder than file approval (`rm -rf` hidden
inside a script; allow-lists vs deny-lists)".

## Decision

Every command is shown in full, and the user answers `Run this command? [y/N]`. Only `y`
or `yes` runs it. No command runs without asking.

## Alternatives considered

- **Allow-list of read-only commands** (`ls`, `cat`, `grep`, `git status`, `git diff`)
  that run without asking. More convenient, but safe matching means parsing shell:
  `ls; rm -rf x`, `cat $(...)`, `git -c core.pager=<anything> log` all start with an
  allowed word. mini-swe-agent does this with a regex whitelist in its `confirm` mode.
  Too much code to get right, too early.
- **Ask, plus an "always" answer** (`[y/N/a]`) that approves the exact command for the
  session. Small and reasonably safe, but not needed for a first version.
- **No prompts** (pi's "YOLO by default"). That goes against what smallkoder is for:
  seeing and approving each change.

## Consequences

- The simplest code, and the same rule for writes and commands.
- Repeated harmless commands (re-running the tests) get tiring. Both alternatives are
  in the backlog as "Fewer command prompts".
- The prompt shows the whole command, however long. Shortening it would mean approving
  something you haven't seen.
