# 0009. `replace_all` is optional and defaults to false

- **Status:** Accepted (decided by the user, 2026-11-11)
- **Date:** 2026-11-11
- **Spec:** [docs/specs/edit-file.md](../specs/edit-file.md)

## Context

The user asked for `replace_all` support, as Claude Code and nanocode have it. Without
it, a rename means one edit per occurrence, or an `old_text` that spans them all.

smallkoder's v0.1 plan writes every schema to OpenAI's strict-mode rules: every property
is in `required`, and a test enforced it. So the first version made `replace_all` a
required boolean. When the traces were recorded, MiMo left it out of its first
`edit_file` call in 2 of the 3 sessions that edited a file. Each time it got
`needs … boolean arguments 'replace_all'`, and retried with `"replace_all": false`: one
wasted model call per edit.

## Decision

`replace_all` is optional. The schema lists it under `properties` but not `required`,
and `parse_arguments` fills in `false` when it is missing. String arguments stay
required.

To support this, `tool_schema()` takes a `flags` argument for optional booleans. The
schema test now checks that every *string* argument is required, instead of every
argument.

## Alternatives considered

- **Keep it required.** It keeps the strict-mode rule, but costs a retry on most edits
  with our default model.
- **Required in the schema, but tolerated when missing.** No retry, but the schema would
  then describe something different from what the code accepts.
- **No `replace_all` at all** (pi's choice). MiMo managed renames without it in the
  benchmark, but the user asked for it.
- **Strict-mode style optional (`"type": ["boolean", "null"]`, still required).** It
  satisfies strict mode, but the model must still send the key, which is the problem.

## Consequences

- After re-recording, MiMo made no argument errors: every edit applied at the first
  call.
- The v0.1 rule "every field required" no longer holds for all tools. `plan.md` records
  the departure. If a provider is ever used with server-side strict mode, `replace_all`
  would have to become required-and-nullable.
- `parse_arguments` now knows about two JSON types, `string` and `boolean`, and fills in
  defaults. That pattern is ready for future optional flags.
