# 0006. Recorded commands run again for real on replay

- **Status:** Accepted
- **Date:** 2026-11-09
- **Spec:** [docs/specs/run-command.md](../specs/run-command.md)

## Context

The recorded-trace tests replay real model sessions. `ReplayModel` serves the recorded
replies, while the loop, the tools and the files run for real, and every request must
match the recording exactly. A command's output goes into the next request, so on replay
the command must print exactly what it printed when recorded.

## Decision

Treat `run_command` like the file tools: on replay it runs for real. Scenarios are chosen
so that their commands give the same output on any machine (`python3 hello.py` and a
declined `rm`, never `ls -l`, `date` or test timings). `scripts/record_traces.py` says so
next to the scenarios.

## Alternatives considered

- **Record command results and serve them back on replay**, like model replies. Any
  command could then appear in a trace, but the replay would no longer test that
  `run_command` really runs things, and the trace format and `ReplayModel` would need a
  second kind of exchange.
- **No command scenarios.** The tool would have no end-to-end test with a real model.

## Consequences

- The replay tests show that commands really run, and that a declined one really
  doesn't (the file survives).
- Only some scenarios can become traces. Replay needs `python3` on `PATH` (true under
  `uv run pytest`).
- A model may choose a command during recording that isn't the same on every machine.
  Re-recorded traces need checking for that (backlog: "Recorded commands must be
  deterministic").
