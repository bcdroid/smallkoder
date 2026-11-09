# Brief: smallkoder, a small CLI code assistant

From Corin Pitcher (instructor). This repo is demonstration material for CSC299
"AI-Assisted Software Development" at DePaul: sophomores with two quarters of Python,
who use Claude Code daily but have never seen inside one. The finished repo (code,
tests, docs, and git history) will be read in class, so optimise for clarity to that
audience over cleverness. Plain Python 3.12, standard library where reasonable.

Work through the steps in order. Commit after each step (small commits, clear messages;
no remote exists, do not add one or push). Never print, log, commit, or echo the API key.
`.env` is already gitignored; keep it that way.

## 1. Check the API key still works

`.env` holds `OPENCODE_GO=sk-...`, a key for OpenCode Go (opencode.ai). Find the correct
endpoint and request format from current official docs (web search/fetch). Make one
minimal request with the cheapest available model (a few tokens), reading the key from
`.env` without displaying it. Report: endpoint, model used, HTTP status, and whether the
key works. If it fails, stop and report rather than working around it.

Reference only (read, do not modify): `~/repos/2026-06-30-pi-opencode` on this machine
may show how pi was configured against OpenCode before. Do not copy secrets from it.

## 2. Research small CLI code assistants

Research how minimal coding agents are built: the agent loop (send messages, receive
tool calls, run tools, append results, repeat until the model stops), tool definitions as
JSON schemas, the OpenAI-compatible chat completions tool-calling format (or whatever
OpenCode Go uses), permission prompts, and system prompts. Look at real small examples,
including pi (https://github.com/earendil-works/pi) and other minimal agents you find.
Cite sources with URLs.

Record it in `docs/research.md`: what you found, with sources, and what it implies for
this project. Commit.

## 3. Plan

Write `docs/plan.md`: a small CLI assistant, `smallkoder`, with an interactive loop and
exactly two tools for this first step:

- `read_file(path)`: returns file contents.
- `write_file(path, content)`: rewrites the entire file. No partial editing yet.

Include in the plan: module layout, the message and tool-call data shapes, how the user
approves writes (a permission prompt), confining paths to the working directory, how the
loop ends, error handling (missing file, bad tool arguments, API errors), and the test
strategy below. Keep the whole program small enough for a student to read in one sitting.
Commit, then proceed to implementation without waiting.

## 4. Implement with TDD throughout

Strict red/green/refactor. For each behaviour: write a failing test, run it and see it
fail, write the least code to pass, run the suite, refactor. Make the history show it:
commit the failing test and the passing code as separate commits where practical (e.g.
"test: ... (red)" then "feat: ... (green)").

This project should illustrate guardrails. Set some up and explain each in the README:

- pytest as the main guardrail, run after every change.
- A Claude Code hook in `.claude/settings.json` that runs the test suite after file
  edits, so failures come back to you automatically.
- A deny rule or hook that stops you from weakening tests to make them pass (e.g. no
  edits to existing test assertions without saying so in the commit message, or no
  `skip`/`xfail`). Choose something that actually works, and record the choice.
- Tests for the tool guardrails in the program itself: writes outside the working
  directory are refused, writes require approval.

### Tests must not need the LLM API

The default `pytest` run must make no network calls, need no key, and be deterministic.

- Put the model behind a small interface (e.g. a `Model` with one `complete(messages,
  tools)` method). The real implementation calls the API; tests use fakes.
- **Scripted fake:** a fake model that returns a fixed sequence of responses, for unit
  tests of the loop (e.g. "first respond with a read_file call, then with a final
  answer").
- **Recorded traces, replayed:** a recorder that wraps the real model and saves each
  request/response pair to a JSON file under `tests/traces/` (no key, no auth headers in
  the file), and a replay model that serves those responses back, checking that each
  request matches what was recorded. Record a handful of real end-to-end sessions once
  (e.g. "read hello.py and add a docstring"), commit the traces, and test against them.
  Document how to re-record.
- Real-API tests, if any, are opt-in only (a marker plus an environment variable),
  skipped by default.
- Fault injection is a nice bonus: a fake that returns malformed tool calls, unknown
  tools, or bad arguments, to test the error handling.

Use your own judgement about scope; prefer finishing a small, clean, working version.

## 5. Backlog

Keep `docs/backlog.md` as a living list of future work, added to as you go (not only at
the end). Start it with at least: a file editing tool (search/replace or apply a patch),
a bash/run-command tool with a permission prompt, listing and searching files, streaming
output, conversation history management and token counting, compaction, cost display,
a system-prompt/AGENTS.md style instruction file, a non-interactive mode (`-p`),
sessions saved to disk, and subagents. Note for each why it is interesting and what it
would teach.

## Finish

Report back briefly: key check result, what was built, how to run it and its tests,
test count, and anything you were unsure about.
