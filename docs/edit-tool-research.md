# Research: an edit tool for smallkoder

Research for the "File editing tool" item in [backlog.md](backlog.md). Gathered
2026-11-09. It covers three things:

- how other coding agents let a model edit files;
- what is known about the edit formats our model, `mimo-v2.6-flash`, was trained on;
- a small benchmark of six edit-tool designs against that model.

The design is not decided yet. The options are listed at the end.

GitHub links are pinned to a commit; line numbers drift on `main`. **[docs≠code]** marks a
place where an agent's documentation and its code disagree. **[unverified]** marks a claim
that could not be checked against a primary source.

## Summary

- **Exact string replacement is the industry default.** The tool is
  `edit(path, old, new)`, and `old` must appear in the file exactly once. Claude Code, pi,
  OpenCode, Gemini CLI, nanocode, Amp's "How to Build an Agent", SWE-agent and
  Anthropic's text editor tool all use it.
- **OpenAI's `apply_patch` format is the exception, and only for GPT models.** OpenAI
  trained its models on it. Some agents (OpenCode, Roo) choose the tool by model family:
  `apply_patch` for GPT, exact replace for everything else.
- **Xiaomi publishes no edit format for MiMo.** The clues all point to exact replace. The
  MiMo-V2-Flash RL scaffold had a tool named `str_replace`. The release notes promise
  "deep integration with Claude Code", whose `Edit` tool is exact replace.
- **Our benchmark agrees.** On `mimo-v2.6-flash`, exact replace succeeded in 60 of 60
  episodes. Every one of its edits applied on the first try, and it used under a quarter of
  the output tokens of whole-file writes. Unified diff, `apply_patch` and hashline all did
  worse. Hashline was worst: 87% on the harder tasks, 4.6× the input tokens, and one
  silent wrong edit.
- **Decision:** `edit_file(path, old_text, new_text, replace_all=false)`, exact match only,
  with error messages the model can act on. `write_file` stays for new files. See
  section 5.

## 1. How agents edit files

### 1.1 Exact string replace, one edit per call

**Claude Code `Edit`.** Claude Code is closed source, so this comes from the docs. The
parameters are `file_path`, `old_string`, `new_string` and `replace_all`. The
[tools reference](https://code.claude.com/docs/en/tools-reference) says it "performs
exact string replacement… doesn't use regex or fuzzy matching". `old_string` must
appear exactly once unless `replace_all` is true, and the file must have been read first.
The error texts are known only from user bug reports **[unverified]**, for example
[issue 3337](https://claudeissues.com/issue/3337-bug-error-found-2-matches-of-the-string-to-replace-but-replace-all-is-false):

- `String to replace not found in file.`
- `Found N matches of the string to replace, but replace_all is false…`

**Anthropic text editor tool**
([docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool)).
It is declared as `{"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}`.
Anthropic defines the schema and the client sends none. Because the schema is fixed and
versioned, the model has presumably been trained on it; that is an inference, since the
docs don't say "trained". The commands are:

- `view` (`path`, `view_range`)
- `str_replace` (`path`, `old_str`, `new_str`)
- `create` (`path`, `file_text`)
- `insert` (`path`, `insert_line`, `insert_text`)

`undo_edit` was removed in the `20250429` version. The docs suggest these errors:
`Found 3 matches for replacement text. Please provide more context to make a unique
match.` and `No match found for replacement. Please check your text and try again.`

**SWE-agent** now uses this tool by default
([default.yaml](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/config/default.yaml)).
Its errors are `No replacement was performed, old_str … did not appear verbatim in …`
and `Multiple occurrences of old_str … in lines [...]. Please ensure it is unique`.

**pi `edit`**
([edit.ts](https://github.com/earendil-works/pi/blob/c9dd2c530160a2c698959771955a682b2b0c5161/packages/coding-agent/src/core/tools/edit.ts),
[edit-diff.ts](https://github.com/earendil-works/pi/blob/c9dd2c530160a2c698959771955a682b2b0c5161/packages/coding-agent/src/core/tools/edit-diff.ts)).

- **Schema.** It takes `{path, edits: [{oldText, newText}]}`. Older calls with top-level
  `oldText`/`newText` are folded into `edits`. It also accepts `edits` sent as a JSON
  string; the code comment says "Some models (Opus 4.6, GLM-5.1) send edits as a JSON
  string".
- **Matching.** Line endings become LF first. Then it tries an exact match. If that fails,
  it retries on normalised text: NFKC, trailing whitespace stripped from each line,
  smart quotes to ASCII, Unicode dashes and spaces to plain ones.
- **Rules.** Each edit is matched against the *original* file and must be unique.
  Overlapping edits are rejected. There is no `replace_all`.
- **Errors:**
  - `Could not find edits[i] in PATH. The oldText must match exactly including all whitespace and newlines.`
  - `Found N occurrences of edits[i]… Each oldText must be unique. Please provide more context to make it unique.`
  - `edits[a] and edits[b] overlap in PATH. Merge them into one edit or target disjoint regions.`
- **[docs≠code]** The schema description says "exact text", but the code has the fuzzy
  fallback.

**Amp, "How to Build an Agent"** ([article](https://ampcode.com/how-to-build-an-agent)).
The tool is `edit_file{path, old_str, new_str}`. An empty `old_str` on a missing file
creates the file. **[docs≠code]** The schema says `old_str` "must only have one match
exactly", but the Go code calls `strings.Replace(old, new, -1)`, which replaces every
match and never checks uniqueness. Errors: `old_str not found in file`,
`invalid input parameters`.

**nanocode**
([nanocode.py](https://github.com/1rgs/nanocode/blob/b009d3dbedf14795a5c10804a5455386563f4b5b/nanocode.py)).
The tool is `edit{path, old, new, all?}`, in about 14 lines of Python, the closest in size
to smallkoder. Errors: `error: old_string not found` and
`error: old_string appears N times, must be unique (use all=true)`.

**Gemini CLI `replace`**
([edit.ts](https://github.com/google-gemini/gemini-cli/blob/5e2f62e7786a7c670f5a5e21ab653ebcd45b7a7d/packages/core/src/tools/edit.ts)).
Parameters: `file_path`, `instruction`, `old_string`, `new_string`, `allow_multiple`.
The `expected_replacements` parameter of 2025 builds is gone. It tries five ways to match,
in order:

1. exact;
2. "flexible": lines compared after trimming, with indentation re-applied;
3. regex;
4. fuzzy: weighted Levenshtein distance, threshold 0.1;
5. a second model call (`FixLLMEditWithInstruction`), which is why there is an
   `instruction` parameter.

Errors: `Could not find an exact match for 'old_string'… please use ReadFile to inspect
the target lines before retrying` and `Failed to edit, Expected 1 occurrence but found
N… set 'allow_multiple' to true.`

**OpenCode `edit`** (`filePath`, `oldString`, `newString`, `replaceAll`).

- **The 1.x line** ([v1.19.5 edit.ts](https://github.com/sst/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/edit.ts))
  had a chain of nine fallback "replacers", credited to Cline's diff evaluations and
  Gemini's editCorrector:
  1. Simple
  2. LineTrimmed
  3. BlockAnchor (first and last lines as anchors, Levenshtein on the middle, threshold 0.65)
  4. WhitespaceNormalized
  5. IndentationFlexible
  6. EscapeNormalized
  7. TrimmedBoundary
  8. ContextAware
  9. MultiOccurrence

  If a replacer's match is not unique, the next one is tried. One guard refuses a match
  "much larger than oldString".
- **The current main branch**
  ([edit.ts](https://github.com/sst/opencode/blob/ae3aa94ef99ed42f1a90144e94841cc59995884b/packages/core/src/tool/plugin/edit.ts))
  cut the chain to three steps: exact, then Unicode quote/dash/space normalisation, then
  ignoring trailing whitespace on each line.
  - On a miss it returns "The closest lines in the file:" with line numbers. It also says
    when `newString is already in the file`.
  - On ambiguity: `Found N matches for oldString, but expected exactly one… or set
    replaceAll to true`.
- **Tool choice by model.** OpenCode swaps `edit`/`write` for `apply_patch` when the model
  id contains `gpt-`, except `gpt-4` and `oss` models
  ([registry.ts](https://github.com/sst/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts)).

### 1.2 Several edits in one call

- **pi** takes `edits[]` (above).
- **Claude Code's `MultiEdit`** (`{file_path, edits: [{old_string, new_string,
  replace_all}]}`, applied in order, all or nothing) is not in the current tools
  reference. Users reported it missing from v2.0.8 on
  ([report](https://claudeissues.com/issue/8994-bug-multiedit-tool-missing-in-version-2-0-8-and-each-llm-request-will-heavily-ca))
  **[unverified]**.
- Text formats are multi-edit by nature: SEARCH/REPLACE blocks, unified-diff hunks,
  `apply_patch` chunks.
- Models with parallel tool calls can also send several single edits in one reply. This
  matters for us (section 3.4).

### 1.3 SEARCH/REPLACE blocks in plain text

**Aider "diff"**
([editblock_coder.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/editblock_coder.py)).
The model writes the file path, then a fenced block:

```
<<<<<<< SEARCH
old lines
=======
new lines
>>>>>>> REPLACE
```

- **Matching.** It tries an exact line match first, and the first occurrence wins, with
  no uniqueness check. Then it tolerates missing leading whitespace, a spurious leading
  blank line, and `...` elisions.
- **[docs≠code]** An edit-distance matcher (`replace_closest_edit_distance`, 0.8) is dead
  code: a bare `return` comes before it.
- **Errors:**
  - `SearchReplaceNoExactMatch: This SEARCH block failed to exactly match lines in PATH`
  - `Did you mean to match some of these actual lines…`
  - `The REPLACE lines are already in PATH!`
  - `The other N blocks were applied successfully. Don't re-send them.`

**Cline `replace_in_file`**
([diff.ts](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/assistant-message/diff.ts)).

- **Format.** The markers are `------- SEARCH` / `=======` / `+++++++ REPLACE`; the old
  `<<<<<<<` markers are still accepted.
- **Matching.** Only the first match is replaced, and blocks must come in file order. It
  falls back from exact to line-trimmed, then block-anchor, then a whole-file search.
- **Recovery.** After 3 failures the model is told to use `write_to_file`.
- **Newer SDK.** Cline's newer SDK replaces this with an `editor{path, old_text,
  new_text, insert_line}` tool plus `apply_patch`
  ([schemas.ts](https://github.com/cline/cline/blob/1e8ae47d60051c5e9a9bd0eed311ef209fdeb347/sdk/packages/core/src/extensions/tools/schemas.ts)).

**Roo Code `apply_diff`**
([multi-search-replace.ts](https://github.com/RooCodeInc/Roo-Code/blob/b867ec9145750d0ae1ff7f02d35406e9bf2a0b16/src/core/diff/strategies/multi-search-replace.ts)).

- **Format.** SEARCH blocks carry a `:start_line:N` hint.
- **Matching.** It uses Levenshtein similarity near that line. The threshold defaults to
  1.0, which means exact.
- **Error.** `No sufficiently similar match found at line: N (X% similar, needs 100%)`,
  plus the best match it found.
- **Tool choice by model.** Roo also chooses by model: `apply_patch` for OpenAI models,
  `search_replace` for MiniMax M2.x and Grok.

### 1.4 Unified diff

**Aider "udiff"**
([post](https://aider.chat/2023/12/21/unified-diffs.html),
[udiff_coder.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/udiff_coder.py)).

- **Format.** It uses the familiar `---`/`+++` and `@@ … @@` lines, but *without* line
  numbers. Each hunk is applied as a search-and-replace on its context and `-` lines.
- **Results.** In Aider's laziness benchmark (89 tasks), gpt-4-1106-preview went from 20%
  to 61% (the "3X less lazy" headline) and gpt-4-0613 from 26% to 59%. Turning off
  flexible patching gave a "9X increase in editing errors".
- **Errors:**
  - `UnifiedDiffNoMatch: hunk failed to apply! … does not contain these N exact lines in a row`
  - `UnifiedDiffNotUnique: … Use additional ' ' lines to provide context…`
- **Today.** Aider makes udiff the default only for the gpt-4-turbo family.

Cursor writes that "models are notoriously bad at counting line numbers"
([instant apply](https://cursor.com/blog/instant-apply)). None of the agents surveyed
pipes model output straight into `git apply` or `patch`; they all re-implement matching
with some tolerance. Our benchmark (section 3) shows why.

### 1.5 OpenAI `apply_patch` (the "V4A" format)

Grammar
([apply_patch.lark](https://github.com/openai/codex/blob/9f04d886f3663b584fba87d6fd71001fb6f9fcf3/codex-rs/core/assets/tools/apply_patch.lark)):

```
*** Begin Patch
*** Update File: src/app.py
@@ def greet():
-    print("hi")
+    print("hello")
*** End Patch
```

- **Full grammar.** It also has `*** Add File:`, `*** Delete File:`, `*** Move to:` and
  `*** End of File`. Context lines start with a space. An `@@ text` line names a nearby
  line, such as a `def`, to search from.
- **Trained on it.** The [GPT-4.1 prompting guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide)
  calls it a format "on which the model has been extensively trained". It asks for 3 lines
  of context above and below each change, and no line numbers. The
  [GPT-5.1 guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5-1_prompting_guide)
  says: "In testing, the named function decreased apply_patch failure rates by 35%."
- **Built-in tool.** The Responses API has it as a built-in tool,
  `tools=[{"type": "apply_patch"}]`
  ([docs](https://developers.openai.com/api/docs/guides/tools-apply-patch)).
- **Matching in Codex**
  ([seek_sequence.rs](https://github.com/openai/codex/blob/9f04d886f3663b584fba87d6fd71001fb6f9fcf3/codex-rs/apply-patch/src/seek_sequence.rs)).
  It makes four passes: exact, trailing whitespace ignored, all surrounding whitespace
  ignored, Unicode punctuation as ASCII. It takes the *first* match at or after the
  current position, with no uniqueness check. An `@@` line moves the position forward.
- **Errors** ([file_update.rs](https://github.com/openai/codex/blob/9f04d886f3663b584fba87d6fd71001fb6f9fcf3/codex-rs/apply-patch/src/file_update.rs)):
  `Failed to find context '…' in PATH`, `Failed to find expected lines in PATH`,
  `Invalid patch hunk on line N`.
- Aider keeps a port of OpenAI's original Python reference
  ([patch_coder.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/patch_coder.py)).

**OpenCode vs. OpenCode Go.** Two different things share the name.

- *OpenCode* is the open-source coding agent above. It gives GPT models `apply_patch`.
- *OpenCode Go* is the API service smallkoder talks to. It has no opinion about edit
  formats: an edit tool is just a schema we send and code we run.

Also, OpenCode Go serves its `gpt-*` models only on `/openai/v1/responses`
([research.md](research.md) section 9). smallkoder only uses chat completions, so it
cannot reach a GPT model today. `apply_patch` would only pay off after a Responses API
adapter is written.

### 1.6 Line-number edits and hashline

**SWE-agent's original `edit <start>:<end>`**
([config](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/tools/windowed_edit_linting/config.yaml),
[paper](https://arxiv.org/html/2405.15793)). On SWE-bench Lite with GPT-4 Turbo:

| Setup | Score |
|---|---|
| edit with a linter | 18.0% |
| edit without a linter | 15.0% |
| no edit command | 10.3% |

The paper reports what went wrong:

- 51.7% of runs had at least one failed edit.
- After one failed edit, the chance of eventual success fell from 90.5% to 57.2%.
- Cascading failed edits caused 23.4% of failures.

Line numbers shift after every edit, and indentation mistakes are common. SWE-agent has
since moved to the exact-replace tool.

**Hashline** (Can Bölük,
["The Harness Problem"](https://stencil.so/blog/the-harness-problem), Feb 2026).

- **Format.** `read` shows each line with a short content hash, like
  `1:a3|function hello() {`. Edits name lines by these tags, and a stale tag (the line
  has changed) is rejected.
- **Results.** On the author's own benchmark (180 React bug-fix tasks, 3 runs, 16
  models), it gained about 15 points on average over patch formats, and up to 61% fewer
  output tokens. Some models gained a lot over patch: MiniMax M2.1 +41.7, GLM-4.7 +23.3.
  The gains over exact replace were smaller: +10 and +8.3 for those two. DeepSeek V3.2 got
  worse (−5 vs patch, −8.3 vs replace). MiMo was not tested.
- **[docs≠code]** The author's current agent (oh-my-pi) uses one 4-hex tag per file plus
  line numbers
  ([hashline.lark](https://github.com/can1357/oh-my-pi/blob/7027a619a41c1eccdae6a5f07de91c43e2a487e3/crates/pi-edit/grammars/hashline.lark)),
  not per-line hashes.

### 1.7 Whole-file rewrite

This is what smallkoder does today, and it is Aider's "whole" format, the fallback when no
model setting matches
([models.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/models.py)).
It costs output tokens and invites `...` elisions, but its edits are nearly always well
formed. On Aider's data, weaker open models did better with "whole" than with "diff":

| Model | whole | diff |
|---|---|---|
| Qwen2.5-Coder-32B | 16.4% (99.6% well formed) | 8.0% (71.6% well formed) |
| Qwen3-32B | 45.8% | 41.3% |

Source: [qwen3_leaderboard.yml](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/_data/qwen3_leaderboard.yml).

### 1.8 "Fast apply" with a second model

The main model writes a sketch with `// ... existing code ...` markers, and a smaller,
fast model merges it into the file. Cursor uses a fine-tuned Llama-3-70B
([instant apply](https://cursor.com/blog/instant-apply)). Morph sells this as a service
([docs](https://docs.morphllm.com/quickstart)) and claims 98% accuracy; that is a vendor
claim. Relace was not checked **[unverified]**. Out of scope for smallkoder: it needs a
second model.

### 1.9 Patterns

- **Matching gets progressively looser.** Every serious implementation tries an exact
  match first, then looser ones: line endings, trailing whitespace, Unicode punctuation,
  then indentation. Only Gemini CLI goes as far as edit distance or another model call.
- **Ambiguity splits the field.** Claude Code, pi, OpenCode, Gemini CLI and nanocode
  return an error when `old` matches more than once, and Anthropic's guidance says the
  same. Aider, Cline and Codex silently take the first match.
- **Some agents choose the format per model family:** `apply_patch` for GPT, exact
  replace for the rest.
- **Matching the trained-in names.** Over chat completions, a model only benefits from
  its "trained-in" format if our tool name and parameters look like it. This is an
  inference, not a vendor statement.

## 2. What our model was trained on

Sources: the [MiMo-V2-Flash technical report](https://arxiv.org/html/2601.02780v1), the
[MiMo release notes](https://mimo.mi.com/docs/en-US/updates/model), the
[tool-call repetition blog post](https://mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition),
[MiMo-Code](https://github.com/XiaomiMiMo/MiMo-Code) and
[OpenRouter's model page](https://openrouter.ai/xiaomi/mimo-v2.6-flash).

- **No edit format is published.** None of these pages give an edit tool's name and
  parameters for MiMo.
- **RL scaffold.** The V2-Flash code-agent RL used "three atomic tools (bash,
  str_replace, finish)". This comes from a summary of the report, not a verbatim quote
  **[unverified]**. The parameter names were not found.
- **Harnesses.** The 2026-01-12 release notes for mimo-v2-flash say "Deep integration
  with Claude Code" and "Optimized Experience for Other Code Agents… such as Kilo, Cline,
  and Roo". These are the only harnesses named. The V2.6 release notes (2026-09-22) say
  nothing about coding agents.
- **MiMo-Code.** Xiaomi's own coding agent is a fork of OpenCode, so it presumably
  inherits OpenCode's exact-replace `edit` tool. Its edit tool source was not checked
  **[unverified]**.
- **Tool-call repetition.** The blog post measures repetition in many harnesses: OpenCode,
  Claude Code, Codex, MiMo Code and others. It does not measure edit success.
- **Aider.** The leaderboard has no MiMo, GLM or MiniMax results. Aider has no settings
  for those models, so it would fall back to "whole".

Every clue points to exact replace. None of them is proof, so we measured.

## 3. Benchmark: six edit tools on `mimo-v2.6-flash`

### 3.1 Method

Each episode starts with the model having already read the file (a seeded `read_file`
call), and asks for one change. The model gets `read_file` plus one edit tool. We apply
its calls with our own implementation of each format, send back any errors, and allow up
to 6 model calls. Then we check the final file by *running* it: the requested behaviour
must work, and everything else must behave as before. The system prompt follows
smallkoder's, with one sentence describing the edit tool.

The six designs:

| Design | Tool | Applied by |
|---|---|---|
| `write_file` | `write_file(path, content)` | Replaces the file (today's tool) |
| `str_replace` | `edit_file(path, old_string, new_string)` | Exact match, must be unique |
| `multi_edit` | `edit_file(path, edits: [{old_string, new_string}])` | Each exact and unique, in order, all or nothing |
| `udiff` | `apply_diff(path, diff)` | Hunks found by content; ties broken by the `@@` line number |
| `apply_patch` | `apply_patch(patch)` | V4A `Update File` only, Codex-style passes (exact, trailing whitespace, all whitespace), first match after the position |
| `hashline` | `replace_lines(path, start, end, new_text)` | `read_file` shows `N:hh\|line`; `start`/`end` are `N:hh` refs; stale refs rejected |

Two task sets, 6 tasks each, 5 repeats, so 30 episodes per design per set:

- **Easy:** an 80-line `inventory.py`. The tasks were:
  - rename a function and its uses;
  - change one of two functions that share identical lines;
  - add a docstring;
  - wrap a line in a check;
  - change two methods;
  - append a function.
- **Hard:** a 235-line `stores.py` holding three near-identical classes (`Shop`,
  `Warehouse`, `Depot`) and 22 lookalike statistics functions. Some lines in `Depot` have
  trailing spaces. The tasks were:
  - change `Warehouse.total` only;
  - rename an attribute in 6 places;
  - change `Depot.sell` on a line with trailing whitespace;
  - fix `geometric_mean`, whose guard lines appear 22 times;
  - delete a function;
  - add a method to all three classes.

Every check was confirmed to fail on the original file and to pass on a hand-written
correct edit before the real runs. In total there were 360 episodes, about 1.67M input
and 0.16M output tokens, costing about $0.28 at $0.14/$0.28 per million.

The benchmark scripts were run from a scratch directory and are not in the repo.

### 3.2 Results

"First try" means the model's first edit call applied without an error. Token figures
are means per episode, summed over all model calls.

**Hard set** (235 lines):

| Design | Pass | First try | Errors / episode | Model calls | Output tokens | Input tokens |
|---|---|---|---|---|---|---|
| `str_replace` | **100%** | **100%** | 0.00 | 2.13 | 412 | 4,014 |
| `multi_edit` | 100% | 100% | 0.00 | 2.10 | 436 | 4,158 |
| `write_file` | 100% | 100% | 0.07 | 2.37 | 1,842 | 6,355 |
| `udiff` | 100% | 70% | 0.30 | 2.53 | 358 | 4,977 |
| `apply_patch` | 97% | 93% | 0.13 | 2.30 | 368 | 4,501 |
| `hashline` | 87% | 83% | 0.30 | 3.80 | 482 | 18,391 |

Passes by task, hard set:

| Design | add3 | deep_dup | delete | dup_class | rename6 | trailing_ws |
|---|---|---|---|---|---|---|
| `str_replace` | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| `multi_edit` | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| `write_file` | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| `udiff` | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| `apply_patch` | 5/5 | 5/5 | 5/5 | 5/5 | 4/5 | 5/5 |
| `hashline` | 4/5 | 5/5 | 5/5 | 5/5 | 2/5 | 5/5 |

**Easy set** (80 lines):

| Design | Pass | First try | Errors / episode | Model calls | Output tokens | Input tokens |
|---|---|---|---|---|---|---|
| `str_replace` | 100% | 100% | 0.00 | 2.00 | 175 | 1,866 |
| `multi_edit` | 100% | 100% | 0.00 | 2.03 | 184 | 2,038 |
| `write_file` | 100% | 100% | 0.00 | 2.00 | 544 | 2,120 |
| `udiff` | 100% | 83% | 0.17 | 2.17 | 184 | 1,987 |
| `apply_patch` | 100% | 93% | 0.07 | 2.07 | 158 | 1,883 |
| `hashline` | 97% | 93% | 0.07 | 2.23 | 176 | 3,444 |

No design produced invalid JSON arguments, and no API call failed.

### 3.3 What the transcripts show

- **Exact replace never failed.** Over 60 episodes it never once hit the "found N times"
  error. Even with three identical classes, the model added the next unique line
  (`return f"Warehouse with …"`) to `old_string` without being told. It also handled the
  trailing-whitespace line 5 times out of 5.
- **The model sends several edits as parallel calls.** For the 6-place rename it sent 3
  or 6 `edit_file` calls in one reply, so an `edits[]` array gave it nothing extra.
  Counts of edits per reply:

  | Task | `str_replace` (edits per reply) | `multi_edit` (edits per call) |
  |---|---|---|
  | rename (easy, 2 spots) | 2 ×5 | 2 ×4, 3 ×1 |
  | add3 (3 spots) | 3 ×5 | 3 ×5 |
  | rename6 (6 spots) | 6 ×2, 3 ×2, 1+1+1 ×1 | 6 ×3, 3 ×2 |

- **Unified diff line numbers were never right.** In 0 of 60 episodes did the `@@ -a,b`
  numbers match the file, so a strict `patch` or `git apply` would have rejected every
  diff. Only matching by content made them work. The model also often left out the `@@`
  lines on its first try (`diff must contain @@ hunk headers`), then fixed it.
- **`apply_patch` anchors were misused.** In the rename task, the model repeated
  `@@ class Shop:` for the second change in the same class. Searching forward from the
  last match, as Codex does, doesn't find it. Once it fell back to smaller patches and ran
  out of calls. A more lenient applier would have passed this.
- **Hashline caused the only silent wrong edit.** On the easy set, the model replaced
  lines 70–72 with new text that left out line 72's content. The code still ran, with a
  line missing and no error. Other hashline problems:
  - Parallel `replace_lines` calls make each other's refs stale, because the first edit
    shifts the line numbers.
  - Rereading the file after each edit made input tokens 4.6× those of exact replace.
  - In the 6-place rename the model sensibly worked bottom-up, one line per call, but ran
    out of the 6-call budget. That failure is partly an artefact of the budget.
- **Whole-file write is reliable but expensive.** It used 4.5× the output tokens of exact
  replace on the 235-line file, and the cost grows with file size. Twice the model tried
  to write a scratch file (`_tmp_fix.py`, `range_mid_block.txt`) instead of the file it
  was asked to change. Those writes were refused, and it recovered.

### 3.4 Limits of the benchmark

- **Scope:** one model, Python only, synthetic files under 250 lines, 6-call budget.
  Long sessions and files of 1000+ lines were not tested.
- **Noise:** 30 episodes per design per set. The top three designs are within noise of
  each other; the gaps to udiff, apply_patch and hashline are clearer.
- **Our appliers:** the failures depend on our own implementations, especially
  `apply_patch`'s forward-only anchors and hashline's refusal of stale refs.
- **Parameter names:** only `old_string`/`new_string` was tested, not pi's
  `old_text`/`new_text`.

## 4. Options for smallkoder

| | Design | Code size (estimate) | For | Against |
|---|---|---|---|---|
| **A** | `edit_file(path, old_string, new_string)` | ~25 lines | Best on MiMo; the industry default; fits the all-string `tool_schema()` | Several edits mean several approval prompts |
| B | `edit_file(path, edits[])` | ~45 lines | One diff and one approval per batch | Needs array support in `tool_schema()`/`parse_arguments`; no gain on MiMo |
| C | `apply_patch` | ~100 lines | GPT's trained-in format | GPT isn't reachable on our endpoint; weaker on MiMo |
| D | Unified diff | ~70 lines | Familiar to students | Must match by content anyway; weaker on MiMo |
| E | Hashline | ~40 lines + `read_file` change | Novel; interesting to teach | Worst on MiMo; changes `read_file` output for every trace |

**Recommendation: A**, exact match only. Options B and C can be added later as backlog
items: B if multi-edit approval becomes annoying, C if a Responses API adapter is ever
written.

These parts are the same whichever design is chosen:

- **Paths and secrets.** It goes through `resolve_path` and the `.env` refusal like the
  other tools. It only edits existing files; `write_file` stays for new files and full
  rewrites.
- **Approval.** It reuses `approve(path, old_text, new_text)`. The diff then shows only
  the change, which also helps with the backlog's "large writes and diffs" item.
- **Errors the model can act on** (in the style of pi and OpenCode):
  - not found, with a hint when it would match if whitespace were ignored;
  - found N times, with the line numbers: "include more surrounding lines";
  - empty `old_string`;
  - `old_string` equal to `new_string`.
- **Matching.** Exact only to start with. MiMo handled trailing whitespace without help,
  so a looser fallback (trailing whitespace, CRLF, Unicode quotes) can be a backlog item.
- **Tests and traces.** The system prompt and tool list change, so all six recorded
  traces must be re-recorded. Add an `edit_function` scenario.

## 5. Decision (2026-11-09)

1. **Design A**: `edit_file`, exact match, unique unless `replace_all`.
2. **Parameter names follow pi**: `old_text`/`new_text`, in snake_case to match
   smallkoder's other arguments (pi itself writes `oldText`/`newText`). The benchmark
   used `old_string`/`new_string`; the new traces show how MiMo does with these names.
3. **`replace_all` is supported**, as an optional boolean that defaults to false. The
   first version made it required, to keep the strict-mode rule (every parameter
   required). When the traces were recorded, MiMo left it out of its first `edit_file`
   call in 2 of 3 sessions and needed a retry each time, so it became optional, as in
   Claude Code, OpenCode and nanocode.

The final schema is `edit_file(path, old_text, new_text, replace_all=false)`. Other design
choices made while building it:

- **Shared with `write_file`.** It uses the same path checks, approval prompt and
  "declined" error. It only edits existing files.
- **Errors.**
  - "old_text not found" adds a hint when the text would match with line-end spaces
    ignored.
  - "appears N times" lists the line numbers.
  - An empty `old_text`, or an edit that changes nothing, is refused.
- **Line endings.** Python's `read_text()` turns `\r\n` into `\n`. So the model's text
  matches CRLF files, but the write converts the file to LF, as `write_file` already did.
  The line-ending conversion is in the backlog.

Follow-ups (looser matching, several edits per call, `apply_patch` for GPT) are in
[backlog.md](backlog.md). The spec is [specs/edit-file.md](specs/edit-file.md); the
decisions are ADRs [0007](adr/0007-edit-by-exact-unique-replacement.md) to
[0011](adr/0011-edits-share-write-approval.md).
