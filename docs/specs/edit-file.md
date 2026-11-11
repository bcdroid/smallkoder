# Spec: `edit_file` tool

- **Status:** implemented (commits `31188f3`..`ac79d51` on branch `edit-file`,
  2026-11-09 to 2026-11-11; merged with `run_command` 2026-11-11)
- **Written:** 2026-11-11, *after* the implementation, from the code, tests and the
  research. The specs-and-ADRs process (ADR 0001) arrived on master while this feature
  was being built on its own branch.
- **Backlog item:** "File editing tool (search/replace or apply a patch)"
- **Research:** [docs/edit-tool-research.md](../edit-tool-research.md) (a survey of
  edit formats, and a benchmark of six designs on `mimo-v2.6-flash`)
- **Decisions:** [ADR 0007](../adr/0007-edit-by-exact-unique-replacement.md),
  [0008](../adr/0008-edit-parameter-names-follow-pi.md),
  [0009](../adr/0009-replace-all-is-optional.md),
  [0010](../adr/0010-exact-matching-only.md),
  [0011](../adr/0011-edits-share-write-approval.md)

## Goal

Let the model change part of an existing file without resending all of it. With only
`write_file`:

- every change costs output tokens for the whole file (4.5× those of an edit on a
  235-line file in the benchmark);
- the model can make mistakes copying long text;
- the approval diff is only as readable as the rewrite is small.

## Non-goals

- **Creating files.** `write_file` still does that.
- **Several replacements in one call** (`edits: [...]`). The model sends parallel calls
  instead (backlog: "Edit tool follow-ups").
- **Fuzzy or whitespace-tolerant matching.** Only a hint in the error
  ([ADR 0010](../adr/0010-exact-matching-only.md)).
- **Patch formats** (unified diff, `apply_patch`), line-number edits, regex.
- **Preserving CRLF line endings** (backlog: "Line endings").
- **Requiring a read before an edit**, as Claude Code does.

## Interface

### Tool schema (sent to the model)

The third entry in `TOOLS` (`smallkoder/tools.py`): after `read_file` and `write_file`,
before `run_command`.

| Field | Value |
|---|---|
| name | `edit_file` |
| parameters | `path`, `old_text`, `new_text` (strings, required); `replace_all` (boolean, optional, default false); no others (`additionalProperties: false`) |
| description | Says: change part of an existing file; `old_text` must match exactly, including indentation and line breaks, and appear exactly once; include surrounding lines to make it unique; `replace_all` replaces every occurrence; the user approves each edit |

`tool_schema(name, description, params, flags=None)` builds it. `params` are required
strings; `flags` are optional booleans and are left out of `required`.
`parse_arguments` fills in a missing flag as `false`, then checks every argument's type
against the schema.

The system prompt names all four tools, and says to use `edit_file` to change part of a
file and `write_file` for new files. It contains no `/`, so traces stay portable.

### Python API

```python
edit_file(root: Path, path: str, old_text: str, new_text: str, replace_all: bool, approve) -> str
run_tool(name, arguments, root, approve, approve_command=never) -> str
```

`approve(path, old_text, new_text) -> bool` is the same callback `write_file` uses. It
receives the whole file before and after the edit, not the two snippets.

## Behaviour

In order:

1. **Read the file** with `read_file`. That brings in every check it has:
   - path outside the working directory;
   - a `.env` file;
   - a directory;
   - a missing file;
   - a file that isn't UTF-8.

   Any failure here happens before the user is asked anything.
2. **Empty `old_text`.** Fail with `old_text is empty. To create a file, use write_file`.
3. **No change.** If `old_text == new_text`, fail with
   `old_text and new_text are the same, so there is nothing to change`.
4. **Find the matches.** `match_lines` returns the line number where each
   non-overlapping occurrence of `old_text` starts. These are the same occurrences
   `str.count` and `str.replace` see.
5. **No match.** Fail with `old_text not found in <path>. It must match the file
   exactly, including indentation and line breaks. Read the file again and copy the
   text.` If the text *would* match with spaces at the ends of lines ignored, add
   `(It would match if spaces at the ends of lines were ignored: check the whitespace.)`
6. **Several matches without `replace_all`.** Fail with:

   ```
   old_text appears <N> times in <path> (lines <a>, <b>, ...). Include more surrounding
   lines so it matches only once, or set replace_all to true to change every one.
   ```
7. **Build the new file.** Replace the first occurrence, or all of them with
   `replace_all`.
8. **Approval.** Call `approve(path, old_file, new_file)`. If it returns false, fail with
   `the user declined this write`. Nothing is written.
9. **Write** the new file as UTF-8. Return
   `Edited <path>: replaced <N> occurrence(s)`, where N is 1 without `replace_all`.

### Line endings

`read_text()` turns `\r\n` into `\n`, so the model sees, and matches against, `\n` only.
The write uses `\n`, so an edit to a CRLF file converts the whole file to LF, as
`write_file` already did. This is a known gap, with a test that pins the current
behaviour.

### Errors

As with every tool, failures are `ToolError`s, which `run_tool` turns into
`Error: ...` results for the model:

| Situation | Tool result |
|---|---|
| Path outside the working directory, `.env`, directory, missing, not UTF-8 | the `read_file` errors (e.g. `Error: file not found: nope.py`) |
| Empty `old_text` | `Error: old_text is empty. To create a file, use write_file` |
| `old_text` equals `new_text` | `Error: old_text and new_text are the same, so there is nothing to change` |
| Not found | `Error: old_text not found in calc.py. It must match…` (+ whitespace hint) |
| Ambiguous | `Error: old_text appears 2 times in calc.py (lines 1, 5). Include more…` |
| User said no | `Error: the user declined this write` |
| Missing string argument, wrong type, extra argument | `Error: edit_file needs string arguments 'path', 'old_text', 'new_text' (and optionally true/false 'replace_all')`, or the usual unexpected-argument error |

## The CLI

The edit goes through the same `approve` as `write_file`. It prints:

```
  The model wants to change calc.py:
--- calc.py
+++ calc.py
@@ -1,4 +1,5 @@
 def add(a, b):
+    """Add two numbers and return the sum."""
     return a + b
  Allow this write? [y/N]
```

The verb is `create` for a new file and `change` otherwise; it used to be `replace`.
Because the diff is between the whole old file and the whole new file, it shows only
the edited lines and their context.

## Guardrails

| Guardrail | `edit_file` |
|---|---|
| Paths confined to the working directory | yes (`read_file`'s check runs first) |
| `.env` refused | yes |
| User approval with a diff | yes, every edit |
| Refused without asking | bad path, missing file, empty or no-op edit, not found, ambiguous |
| Can't land in the wrong place | an ambiguous `old_text` is refused unless `replace_all` |
| Errors as results, step limit | yes |

## Traces

- `edit_function`: change `sub` in a file with two near-identical functions. The test
  checks that `edit_file` was used, `write_file` was not, and only `sub` changed.
- `rename_everywhere`: rename a parameter used in 3 of 12 functions in a 54-line file.
  The test checks that `edit_file` was used and the renamed functions still work.
- `add_docstring` and `declined_write` also use `edit_file` since it was added.

## Tests

| Behaviour | Test |
|---|---|
| Unique replacement, multi-line text, deletion | `tests/test_tools.py::test_edit_file_replaces_unique_text`, `..._can_span_lines`, `..._new_text_can_be_empty_to_delete` |
| Not found, whitespace hint, CRLF behaviour | `test_edit_file_not_found`, `..._not_found_hints_at_whitespace`, `..._crlf_file_matches_lf_text` |
| Ambiguous: count and line numbers, refused before asking | `test_edit_file_ambiguous_says_how_many_and_where` |
| `replace_all` | `test_edit_file_replace_all`, `..._replace_all_with_one_match` |
| Empty, no-op, missing file | `test_edit_file_empty_old_text`, `..._no_change`, `..._missing_file` |
| Declined, outside root, `.env` | `test_edit_file_declined_leaves_file_alone`, `..._outside_root_is_refused_without_asking`, `..._refuses_env` |
| Schema, optional flag, every string required | `test_edit_file_schema`, `test_tool_schemas_require_every_string_argument`, `test_tools_are_exactly_the_file_tools_and_run_command` |
| Argument checks via `run_tool` | `test_run_tool_edit*` |
| Agent loop, system prompt | `tests/test_agent.py::test_edit_file_round_trip`, `test_system_prompt_mentions_edit_file` |
| CLI: diff of the change, "wants to change", same prompt | `tests/test_cli.py::test_edit_shows_only_the_change_and_asks` |
| Real model sessions | `tests/test_recorded_sessions.py::test_edit_function_changes_only_sub`, `test_rename_everywhere_uses_edit_file` |

## Known gaps

- **CRLF files become LF** on any edit (backlog: "Line endings").
- **Only exact matches.** A near miss gets a hint, not a fix (backlog: "Edit tool
  follow-ups", looser matching).
- **One approval per call.** A 6-place rename sent as 6 parallel calls means 6 prompts
  (backlog: several edits in one call).
- **No read-before-edit check.** The model can edit a file it hasn't read, guessing
  `old_text`. An exact match makes a wrong guess fail rather than land, but a stale
  view of a file the user changed meanwhile isn't detected.
- **Time of check vs. time of write.** The file is read, the user is asked, then the new
  text is written. A change made to the file while the prompt is open is overwritten.
  The symlink race noted in the backlog also applies.
