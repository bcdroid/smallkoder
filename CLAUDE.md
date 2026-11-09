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
