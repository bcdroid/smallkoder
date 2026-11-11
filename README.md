# smallkoder

A small command-line coding assistant, written to be read. It is the same idea as
Claude Code, pi or Codex, cut down to about 560 lines of plain Python: an
interactive loop, one model API, and three tools.

```
$ smallkoder
smallkoder (mimo-v2.6-flash) in /home/me/demo. Type 'exit' or Ctrl-D to quit.
> Add a docstring to the add function in calc.py
  [read_file] {"path": "calc.py"}
  [write_file] {"path": "calc.py", "content": "def add(a, b):\n    \"\"\"Ad...
  The model wants to replace calc.py:
--- calc.py
+++ calc.py
@@ -1,2 +1,3 @@
 def add(a, b):
+    """Add two numbers and return the sum."""
     return a + b
  Allow this write? [y/N] y
Added a docstring to `add` in calc.py.
> exit
```

Background: [docs/research.md](docs/research.md) (how agents like this work, with
sources), [docs/plan.md](docs/plan.md) (the design), [docs/backlog.md](docs/backlog.md)
(what to build next), [docs/brief.md](docs/brief.md) (the original assignment),
[docs/session-notes.md](docs/session-notes.md) (report and lessons from the build session),
[docs/specs/](docs/specs) (one spec per feature added since v0.1) and
[docs/adr/](docs/adr) (the decisions behind them, and the alternatives rejected).

## Running it

You need [uv](https://docs.astral.sh/uv/) and an [OpenCode Go](https://opencode.ai) API key.
uv installs Python 3.12+ if needed.

**Use uv for all package management**: `uv sync` to set up, `uv add <pkg>` (or
`uv add --dev <pkg>`) to add a dependency, `uv run ...` to run things. Not `pip`, and
don't edit dependency lists in `pyproject.toml` by hand. Commit `uv.lock` with any
dependency change.

```sh
echo 'OPENCODE_GO=your-key-here' > .env      # .env is gitignored; never commit it
uv sync                                      # create .venv with smallkoder and pytest
uv run scripts/check_key.py                  # optional: one tiny request to test the key
uv run smallkoder                            # from this directory
```

To use it in another project, install it (`uv tool install -e .`) and run `smallkoder` there,
with `OPENCODE_GO` set in your environment or in that project's `.env`. Pick a different
model with `--model glm-5.3-flash`. The default, `mimo-v2.6-flash`, is the cheapest
OpenCode Go model on the chat completions API.

## Reading the code

Suggested order:

| File | Lines | What it does |
|---|---|---|
| [`smallkoder/tools.py`](smallkoder/tools.py) | 199 | `read_file`, `write_file`, `run_command`, their JSON schemas, path checks, and `run_tool`, which turns every problem into an `Error: ...` string for the model |
| [`smallkoder/agent.py`](smallkoder/agent.py) | 50 | **The agent loop.** Ask the model; if it wants tools, run them, append the results, and ask again; stop when it answers |
| [`smallkoder/model.py`](smallkoder/model.py) | 107 | The only network code: one HTTP POST to OpenCode Go with `urllib` |
| [`smallkoder/cli.py`](smallkoder/cli.py) | 85 | The prompt, the approval questions (a diff for writes, the full command for commands), Ctrl-D, API-error recovery |
| [`smallkoder/traces.py`](smallkoder/traces.py) | 110 | Recording real sessions and replaying them in tests |

Messages are plain dicts in the OpenAI chat completions format, the same as what goes
over the wire. A model is anything with a `complete(messages, tools)` method, which is
what lets the tests swap in fakes.

## Tests

```sh
uv run pytest               # 158 tests, ~2.5 s, no network, no key needed
```

| Kind | Where | What it shows |
|---|---|---|
| Unit tests | `test_tools.py`, `test_model.py` | Each function, including every error path |
| **Scripted fake model** | `test_agent.py`, `test_cli.py`, [`fakes.py`](tests/fakes.py) | `ScriptedModel([tool_calls(...), answer(...)])` plays the model: "first ask to read hello.py, then answer". Tests the loop with no API |
| **Fault injection** | `test_agent.py`, `test_cli.py`, `test_model.py` | Fakes that send invalid JSON arguments, unknown tools, missing arguments, endless tool calls, HTTP errors, malformed responses |
| **Recorded traces, replayed** | `test_recorded_sessions.py`, [`tests/traces/`](tests/traces) | Eight real sessions with the real model, saved as JSON. `ReplayModel` serves the recorded replies and fails if our code sends anything different. The loop, tools, files and commands all run for real, so recorded commands must give the same output on any machine |
| Live API | `test_live.py` | Opt-in only: `SMALLKODER_LIVE=1 uv run pytest -m live` |
| The guardrails themselves | `test_guardrails.py`, `test_guard_hook.py` | The network block and the Claude Code hook below |

### Re-recording the traces

Replay compares every request exactly. So if you change the system prompt, a tool
description or the message format, the trace tests fail with a `TraceMismatch` that shows
the first differing message. That is deliberate: you changed what the model sees. To
re-record (needs the key; costs well under a cent):

```sh
uv run scripts/record_traces.py                  # all scenarios
uv run scripts/record_traces.py add_docstring    # just one
```

Scenarios are defined at the top of [`scripts/record_traces.py`](scripts/record_traces.py).
The model may answer differently each time, so after re-recording run `uv run pytest`, check
the per-scenario tests still pass (e.g. "the declined write left the file alone"), and
look at `git diff tests/traces` before committing. Only messages and replies are recorded,
never the key or HTTP headers, and a test checks that.

## Guardrails

This project is also a demonstration of guardrails: checks that don't rely on anyone
(human or AI) remembering to be careful.

### In the program: what the model is allowed to do

1. **File paths are confined to the working directory.** `resolve_path` resolves `..`
   and symlinks *first*, then checks the result is inside the working directory. That
   catches `../secret.txt`, `/etc/passwd`, and a symlink pointing outside. The check is
   in code, not in the system prompt: a prompt is a request, code is a guarantee. The
   `outside_workspace` trace shows a real model getting refused.
2. **Every write needs approval.** `write_file` shows a diff and asks `[y/N]`; anything
   but `y`/`yes` (including Ctrl-D) means no. A declined write is reported to the model
   as an error, so it knows. (pi deliberately has no prompts; we keep one because seeing
   and approving each change is the point here.)
3. **`.env` files are off limits** to `read_file` and `write_file`, so the model can't
   read our API key with them and send it to the API.
4. **Every command needs approval, and that is its only guardrail.** `run_command` shows
   the full command (never shortened) and asks `Run this command? [y/N]`. Rules 1 and 3
   do **not** apply to commands: `cat ../secret.txt` or `cat .env` would work if you said
   yes. Checking the command text can't fix that, because a shell has endless ways to
   say the same thing (`cat .e*`, `sh -c "$(echo ...)"`, a script the model wrote a
   moment ago). This is why command approval is harder than file approval, and why real
   tools add a sandbox. What code *can* guarantee, it does:
   - `OPENCODE_GO` is removed from the command's environment, so `echo $OPENCODE_GO`
     prints nothing (the `.env` file on disk is another matter).
   - stdin is closed, so a command waiting for input gets EOF instead of hanging.
   - A 30 s timeout. The command runs in its own process group, and a timeout or Ctrl-C
     kills the whole group, so `server &` can't outlive it.
   - Only the last 10,000 characters of output go back to the model.
5. **Bad tool calls never crash the program.** They become `Error: ...` results the
   model can read and fix.
6. **A step limit** (20 model calls per turn) stops a model that never stops calling tools.

### In the tests: keeping the suite honest

7. **The default `pytest` run cannot touch the network.** An autouse fixture in
   [`tests/conftest.py`](tests/conftest.py) replaces `socket.connect` and DNS lookups
   with an error, except in tests marked `live`. An accidental real API call fails loudly.
8. **Secrets never reach traces**, by design (`complete()` never sees the key) and by test.

### Around the developer: Claude Code hooks

This repo was built with Claude Code, and [`.claude/settings.json`](.claude/settings.json)
sets up two hooks that apply to anyone (or any agent) editing it with Claude Code:

9. **pytest runs after every edit.** A `PostToolUse` hook on `Edit|Write`
   ([`run_tests.sh`](.claude/hooks/run_tests.sh)) runs the suite after every file
   change. If it fails, the hook exits with code 2, which sends the failure output back
   to Claude straight away, while it is still looking at the change that caused it.
   (Exit code 1 would only go to a debug log.) In the red step of TDD this is expected
   and useful: it confirms the new test fails for the right reason.

10. **Tests can't be quietly weakened.** A `PreToolUse` hook on `Edit|Write`
    ([`guard_tests.py`](.claude/hooks/guard_tests.py)) inspects edits to `tests/**/*.py`
    *before* they happen, and blocks (exit 2) any that:
    - add a skip or xfail (`pytest.mark.skip`, `pytest.skip()`, `xfail`, `unittest.skip`, ...), or
    - remove or change an existing `assert` or `pytest.raises` line (comparing old and new text).

    **Why this design.** The tempting failure for an AI (or a tired human) is to make a
    red test green by loosening the test. A blanket deny rule such as `Edit(tests/**)`
    would also block writing new tests, which TDD needs constantly. Instead, the hook
    allows *adding* tests and assertions freely, and changing them only *visibly*: if a
    line carries a `# test-guard: <reason>` comment, the hook lets it through. The change
    still happens, but the reason is in the diff for a reviewer, and the convention is
    to mention it in the commit message too.

    It fired for real while building this. When the design of `on_tool` changed before
    its test was ever committed, the guard blocked the assertion change, and the final
    version carries a `# test-guard:` comment (see `tests/test_agent.py` and
    `git show 37dfab7`). It is itself tested, by running it as a
    subprocess with the same JSON Claude Code sends.

**Limits, honestly.** These hooks catch mistakes; they are not a security boundary.
Changes made through the shell (`sed`, `python -c`, `rm tests/...`) do not trigger
`Edit|Write` hooks, and someone can always add a `# test-guard:` comment. pytest
itself is still the main guardrail; the hooks make sure it runs and isn't defanged.

## Git history

The history follows red/green/refactor. Most behaviours have a `test: ... (red)` commit
with the failing tests, then a `feat: ... (green)` commit with the code that makes them
pass, sometimes followed by a `refactor:`. Try `git log --oneline` and
`git show <commit>` for any pair.
