# smallkoder

A small coding assistant, written to be read in class. See [README.md](README.md) for
how it works, and its Guardrails section for the hooks that run on your edits.

## Package management: uv only

- Use uv for everything: `uv sync`, `uv add <pkg>`, `uv add --dev <pkg>`, `uv remove`,
  `uv run ...`. Never use `pip`, and never edit the dependency lists in `pyproject.toml`
  by hand.
- Commit `uv.lock` with any dependency change.
- Run things with `uv run`: `uv run pytest`, `uv run smallkoder`,
  `uv run scripts/record_traces.py`.

## Working here

- Tests: `uv run pytest`, which is offline and needs no key. The live test is opt-in:
  `SMALLKODER_LIVE=1 uv run pytest -m live`.
- Changing the system prompt, a tool schema or the message format breaks the
  recorded-trace tests on purpose. Re-record with `uv run scripts/record_traces.py`,
  then read `git diff tests/traces`.
- Never read, print or commit `.env`, which holds the API key.
- Add new ideas to [docs/backlog.md](docs/backlog.md) as they come up. Keep the
  `docs/plan.md` text as written, and record departures from it under "What changed
  during implementation".

## Specs and ADRs for every feature

Use this approach for all new features (see [docs/adr/0001](docs/adr/0001-record-architecture-decisions.md)):

1. **Spec first.** Before any code, write `docs/specs/<feature>.md`: goal, non-goals,
   interface, behaviour, errors, guardrails, tests, known gaps.
   [docs/specs/run-command.md](docs/specs/run-command.md) is the model to follow.
2. **An ADR for each decision with real alternatives.** Write
   `docs/adr/NNNN-<slug>.md` from the template in [docs/adr/README.md](docs/adr/README.md),
   and add it to that index. If the decision is the user's to make (guardrails,
   spending money, approval policy), ask first, then record their answer in the ADR.
3. **Commit the spec and ADRs before or with the red tests.** If implementation
   changes the design, update the spec in the same commit. Never edit an accepted
   ADR to change a decision: write a new ADR that supersedes it.
4. Small fixes and refactors don't need a spec. Add an ADR only if they make a real
   design choice.
