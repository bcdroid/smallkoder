# Architecture decision records

One short file per decision that had real alternatives, in the format of
[Michael Nygard's ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
the context, the decision, the alternatives, and what follows from it. ADRs are never
edited to change a decision. A new ADR supersedes the old one, and the old one's status
says so.

Feature specs live in [`docs/specs/`](../specs). A spec says *what* a feature does; an ADR
says *why* one option was chosen over another.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record decisions as ADRs, and write a spec for each feature | Accepted |
| [0002](0002-approve-every-command.md) | `run_command` asks about every command | Accepted |
| [0003](0003-approval-is-the-only-command-guardrail.md) | Approval is the only guardrail for commands; the key is hidden from their environment | Accepted |
| [0004](0004-separate-command-approval-callback.md) | A separate `approve_command` callback that declines by default | Accepted |
| [0005](0005-kill-the-whole-process-group.md) | Commands run in their own process group, killed whole on timeout or Ctrl-C | Accepted |
| [0006](0006-recorded-commands-run-for-real-on-replay.md) | Recorded commands run again for real on replay | Accepted |
| [0007](0007-edit-by-exact-unique-replacement.md) | `edit_file` replaces exact text that appears once (over diffs, `apply_patch`, hashline, multi-edit) | Accepted |
| [0008](0008-edit-parameter-names-follow-pi.md) | `edit_file`'s parameters follow pi: `old_text`, `new_text` | Accepted |
| [0009](0009-replace-all-is-optional.md) | `replace_all` is optional and defaults to false | Accepted |
| [0010](0010-exact-matching-only.md) | Exact matching only, with a whitespace hint instead of a fallback | Accepted |
| [0011](0011-edits-share-write-approval.md) | Edits are approved like writes: same callback, whole-file diff, same prompt | Accepted |

## Template

```markdown
# NNNN. Title in the imperative or as a statement

- **Status:** Proposed | Accepted | Superseded by [NNNN](...)
- **Date:** YYYY-MM-DD
- **Spec:** [docs/specs/<feature>.md](../specs/<feature>.md) (if any)

## Context
What forces are at play; what problem needs deciding.

## Decision
What we chose, stated plainly.

## Alternatives considered
Each option not taken, and why.

## Consequences
What becomes easier, what becomes harder, what follow-up work it creates.
```
