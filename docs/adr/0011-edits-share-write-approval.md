# 0011. Edits are approved like writes: same callback, whole-file diff, same prompt

- **Status:** Accepted
- **Date:** 2026-11-09
- **Spec:** [docs/specs/edit-file.md](../specs/edit-file.md)

## Context

Every write already goes through `approve(path, old_text, new_text) -> bool`. The CLI
shows a unified diff of the old and new file and asks `Allow this write? [y/N]`. An edit
changes a file too, so it needs the same approval.

`run_command` got its own callback ([ADR 0004](0004-separate-command-approval-callback.md))
because a command has no path and no diff. An edit has both.

## Decision

- `edit_file` calls the existing `approve`, passing the *whole* file before and after
  the edit. The CLI's diff then shows just the changed lines and their context.
- The prompt is unchanged (`Allow this write? [y/N]`), and a decline returns the same
  error as a declined write: `the user declined this write`.
- The CLI's heading changes from "wants to replace" to "wants to change", which is true
  for both tools.

## Alternatives considered

- **A separate `approve_edit(path, old_text, new_text)`** showing only the two snippets.
  It means another callback through `run_turn` and `run_tool`, and the user would see
  the replacement without its surroundings.
- **A different decline message** ("declined this edit"). More precise, but the prompt
  says "write", the system prompt says "if they decline, do not try again", and the
  `declined_write` trace already checks the existing message.
- **Leave the heading as "replace".** It would be wrong for a one-line edit.

## Consequences

- No new callback. Every approver that handles writes (the CLI, tests, the trace
  recorder and replay) handles edits unchanged.
- A trace's `approvals` list doesn't say whether an answer was for a write or an edit.
  The tool call before it does.
- Several edits mean several prompts. One prompt per batch would need several edits in
  one call (backlog: "Edit tool follow-ups").
