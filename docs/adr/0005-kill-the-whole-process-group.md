# 0005. Commands run in their own process group, killed whole on timeout or Ctrl-C

- **Status:** Accepted
- **Date:** 2026-11-09
- **Spec:** [docs/specs/run-command.md](../specs/run-command.md)

## Context

A command must not hang smallkoder. The obvious tool, `subprocess.run(..., timeout=30)`,
kills only the direct child (`bash`) when time runs out. If the command started a
background process (`server &`, `sleep 30 & echo started`), that process still holds
the output pipe open. `run()` then waits again, possibly forever. Ctrl-C has a related
problem: when the command shares smallkoder's process group, the terminal sends SIGINT
to both, and how the command handles it is out of our control.

## Decision

Start the command with `start_new_session=True`, so it and everything it starts share a
new process group. On timeout, or on any exception while waiting (Ctrl-C raises
`KeyboardInterrupt` in smallkoder only, since the command is no longer in the terminal's
foreground group), send `SIGKILL` to the whole group with `os.killpg`, reap the process,
and then report the timeout or re-raise.

## Alternatives considered

- **`subprocess.run(timeout=...)`.** Simple, but it hangs on background children, the
  case this decision exists for.
- **Kill only the child, then read the pipe with a second timeout.** The background
  process would keep running after smallkoder gave up on it.
- **Track the process tree (psutil).** A dependency, and racy.

## Consequences

- Timeouts are reliable; tests check both the timeout and the Ctrl-C path.
- POSIX only: `start_new_session` and `os.killpg` don't exist on Windows (backlog).
- A process that calls `setsid` itself leaves the group and survives.
- Because the command has no controlling terminal, programs that open `/dev/tty` (sudo
  password prompts, for example) fail instead of waiting. That is intended.
