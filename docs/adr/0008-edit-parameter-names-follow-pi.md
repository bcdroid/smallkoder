# 0008. `edit_file`'s parameters are named after pi's: `old_text` and `new_text`

- **Status:** Accepted (decided by the user, 2026-11-09; recorded 2026-11-11)
- **Date:** 2026-11-09
- **Spec:** [docs/specs/edit-file.md](../specs/edit-file.md)

## Context

Agents with an exact-replace tool name its parameters differently. Over chat
completions, a model benefits from a format it was trained on only if our names look
like the trained-in ones. That is an inference, not a vendor statement.

| Agent | Names |
|---|---|
| Claude Code | `old_string`, `new_string`, `replace_all` |
| pi | `oldText`, `newText` (inside `edits[]`) |
| Anthropic text editor tool | `old_str`, `new_str` |
| OpenCode | `oldString`, `newString`, `replaceAll` |
| nanocode | `old`, `new`, `all` |

The benchmark used `old_string`/`new_string`. Xiaomi's notes mention Claude Code
integration, which slightly favours Claude Code's names.

## Decision

Follow pi: `old_text` and `new_text`, in snake_case like smallkoder's other arguments
(`path`, `content`, `command`). The flag is `replace_all`.

## Alternatives considered

- **`old_string`/`new_string`** (Claude Code). What the benchmark measured, and possibly
  closer to MiMo's training. "String" is a type name rather than a description of the
  content.
- **pi's exact spelling, `oldText`/`newText`.** It would mix camelCase into otherwise
  snake_case schemas.
- **`old`/`new`** (nanocode). Shortest, but less clear in an error message ("old not
  found").

## Consequences

- The names read naturally in error messages: "old_text appears 2 times…".
- The benchmark's evidence is for different names. The recorded traces show MiMo using
  `old_text`/`new_text` correctly in every edit, with no argument errors once
  `replace_all` became optional ([ADR 0009](0009-replace-all-is-optional.md)).
