# 0007. Edit files by replacing exact text that appears once

- **Status:** Accepted (decided by the user, 2026-11-09; recorded 2026-11-11)
- **Date:** 2026-11-09
- **Spec:** [docs/specs/edit-file.md](../specs/edit-file.md)

## Context

`write_file` resends the whole file for every change. That costs output tokens, invites
copying mistakes, and makes the approval diff only as small as the rewrite. Coding
agents give their models many different edit formats. Which one a model handles well
depends on what it was trained on. Xiaomi publishes no edit format for MiMo, our
default model, though its RL scaffold had a `str_replace` tool and its release notes
promise Claude Code integration.

Six designs were surveyed and benchmarked on `mimo-v2.6-flash`: 360 episodes, two task
sets, checked by running the edited code
([edit-tool-research.md](../edit-tool-research.md) sections 3–4). On the hard set (a
235-line file of near-duplicate code):

| Design | Pass | Edit worked first time | Output tokens | Input tokens |
|---|---|---|---|---|
| Exact replace | 100% | 100% | 412 | 4.0k |
| Several replacements per call | 100% | 100% | 436 | 4.2k |
| Whole-file write | 100% | 100% | 1,842 | 6.4k |
| Unified diff | 100% | 70% | 358 | 5.0k |
| `apply_patch` | 97% | 93% | 368 | 4.5k |
| Hashline | 87% | 83% | 482 | 18.4k |

## Decision

Add `edit_file(path, old_text, new_text, replace_all)`. It replaces `old_text`, which
must match the file exactly and appear exactly once unless `replace_all` is true. It
only edits existing files; `write_file` stays for creating and rewriting them.

## Alternatives considered

- **Several replacements in one call** (`edits: [...]`, pi's design). Just as accurate,
  but no better on MiMo, which sends parallel calls instead. It needs array-of-object
  schemas and validation, about twice the code. It would give one approval prompt per
  batch; kept in the backlog for that reason.
- **OpenAI `apply_patch`** (V4A format, Codex). GPT models were trained on it, and
  OpenCode gives it to GPT models only. It needs a ~100-line parser. GPT isn't
  reachable through smallkoder's chat completions endpoint, and MiMo was weaker with it:
  it reused `@@` anchors that a forward-only search can't find.
- **Unified diff.** Familiar to students. MiMo got the `@@` line numbers wrong in all
  60 episodes, so hunks have to be found by content anyway (as Aider does). It often
  left out the `@@` lines on its first try.
- **Hashline** (each line tagged with a short hash; edits name line ranges). Worst on
  MiMo:
  - parallel edits made each other's line references stale;
  - rereading the file cost 4.6× the input tokens;
  - it produced the benchmark's only silent wrong edit (a line dropped from a range).

  It would also change `read_file`'s output for every trace.
- **Keep `write_file` only.** Reliable on small files, but the cost grows with file size,
  and the approval diff with it.

## Consequences

- The most common design in other agents (Claude Code, pi, OpenCode, Gemini CLI,
  nanocode, Anthropic's text editor tool). About 25 lines of code, with error messages
  the model can act on.
- Because a match must be unique, an edit can't land in the wrong place. The model has
  to include enough context, which MiMo did without being told: no ambiguity errors in
  60 benchmark episodes.
- Edits that touch several places mean several calls and several approval prompts.
- Follow-ups are in the backlog: looser matching, several edits per call, and
  `apply_patch` for GPT models after a Responses API adapter.
