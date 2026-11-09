# Session notes, 2026-11-09

What happened while building smallkoder v0.1 with Claude Code, following
[brief.md](brief.md). This is the end-of-session report plus a few things learned along
the way that don't belong in the code.

## Report

**Key check (step 1).** The key works. One request to
`POST https://opencode.ai/inference/go/openai/v1/chat/completions` with model
`mimo-v2.6-flash` (the cheapest model on that endpoint) returned HTTP 200 for 19
tokens. OpenCode Go also requires an `x-opencode-session: ses_...` header; requests
without it get `400 MissingSessionID`. Tool calls come back in the standard OpenAI shape,
plus extra `reasoning` fields that smallkoder ignores. Re-check any time with
`python scripts/check_key.py`.

**What was built (steps 2-5).**

- [research.md](research.md), [plan.md](plan.md), [backlog.md](backlog.md) (kept up
  while building), and the [README](../README.md), which explains every guardrail.
- `smallkoder`, about 460 lines of standard-library Python: an interactive loop with
  `read_file` and `write_file`.
  - Each write shows a diff and asks; anything but `y` means no.
  - Paths are limited to the working directory (`../`, absolute paths and symlinks
    pointing outside are refused), and `.env` files are refused so the model can't
    read the key.
  - Bad tool calls come back to the model as `Error: ...` text instead of crashing.
    API errors roll the conversation back so the user can retry.
- Tests: 125 run by default in about 0.5 s with no network and no key, plus 1 opt-in
  live test.
  - Scripted fakes drive the loop and CLI tests.
  - Fault-injecting fakes send bad JSON, unknown tools, endless tool calls, HTTP errors
    and malformed responses.
  - Six real sessions are recorded in `tests/traces/` and replayed with an exact match
    on every request.
  - A fixture in `tests/conftest.py` blocks connections and DNS lookups in every test
    not marked `live`.
- Claude Code hooks in `.claude/settings.json`, both active during the session:
  - pytest runs after every Edit/Write and failures come straight back to Claude.
  - Skips, xfails and removed or changed assertions under `tests/` are blocked unless
    the line carries `# test-guard: <reason>`. It blocked one deliberate design change,
    which now carries the comment (commit `37dfab7`).

**How to run.** See the README: `python -m smallkoder`; tests with
`python -m pytest`; live test with `SMALLKODER_LIVE=1 python -m pytest -m live`;
re-record traces with `python scripts/record_traces.py`.

## Things to know, and open questions

- **Red/green order has exceptions.** Most behaviours have a `test: ... (red)` commit
  then a `feat: ... (green)` commit. The exceptions:
  - The replay tests (`4604a9d`) check committed recordings, so they passed on their
    first run. To make sure they *can* fail, one word of the system prompt was changed
    temporarily: 11 replay tests failed with `TraceMismatch`.
  - The guard-hook tests took three red commits (`1ddbc6b`, `9921d83`, `f630bf4`)
    because the tests themselves had mistakes. One was that Python exits with code 2
    when a script file is missing, the same code the hook uses to block, so some
    "blocked" tests passed before the hook existed. Blocks now also have to print the
    override instructions.
  - Project setup, the network fixture and the trace recording were committed without
    a red step.
- **The hooks can be bypassed.** They don't fire for changes made through the shell
  (`sed`, `python -c`, `rm`), and anyone can add a `# test-guard:` comment. They catch
  mistakes; they are not a security boundary. Closing the gap is in the backlog.
- **Endpoint drift.** Some third-party pages still give an older base URL,
  `https://opencode.ai/zen/go/v1`. The code follows the current official docs.
- **Recorded answers vary.** `mimo-v2.6-flash` handled all six scenarios as intended,
  but a model's wording changes from run to run. So the per-scenario tests check what
  happened (the declined write left the file alone, the missing file produced an error
  result), not the exact text. After re-recording, read `git diff tests/traces`.

## Pitfall: Python's cache can hide a quick edit

While checking that the replay tests could fail, the experiment was: change "short" to
"brief" in `SYSTEM_PROMPT`, run the tests (11 failed, as expected), restore the file
with `git checkout`, run again. The second run *still* failed 11 tests.

The cause was Python's bytecode cache. `__pycache__/*.pyc` files are reused when the
source file's modification time (to the second) and size are unchanged. "short" and
"brief" are the same length, and the edit and the restore happened within one second,
so Python reused the cached bytecode of the *edited* file. Deleting `__pycache__` fixed
it, and all tests passed.

This only bites with scripted same-size edits made very quickly. When an experiment like
this behaves oddly, clear the cache first (`find . -name __pycache__ -exec rm -rf {} +`)
or run with `PYTHONDONTWRITEBYTECODE=1`.
