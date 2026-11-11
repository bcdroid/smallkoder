# 0010. Match `old_text` exactly, with a whitespace hint instead of a fallback

- **Status:** Accepted
- **Date:** 2026-11-09
- **Spec:** [docs/specs/edit-file.md](../specs/edit-file.md)

## Context

Models sometimes copy text almost but not quite right. Common slips are trailing
spaces, tabs versus spaces, smart quotes and CRLF line endings. Agents differ in how
much they forgive:

- **Claude Code and nanocode:** exact only.
- **pi:** exact, then a match on normalised text (trailing whitespace, Unicode quotes,
  dashes and spaces).
- **Codex `apply_patch`:** exact, then ignoring trailing whitespace, then all
  surrounding whitespace, then Unicode punctuation as ASCII.
- **OpenCode:** a 9-step fallback chain in 1.x, cut back to 3 steps later.
- **Gemini CLI:** exact, flexible, regex and fuzzy matching, then a second model call.

Looser matching rescues near misses, but each step adds code and a chance of editing
the wrong text.

## Decision

Match exactly, after Python's universal-newline translation. If there is no match, but
there would be with spaces at the ends of lines ignored, say so in the error
("check the whitespace") and let the model retry.

## Alternatives considered

- **Normalise and retry** (pi, Codex). Tolerates trailing whitespace and Unicode
  punctuation. A good next step, kept in the backlog. It needs care to rewrite only the
  matched lines and keep the rest of the file byte for byte.
- **Fuzzy matching** (edit distance, as in Gemini CLI and OpenCode 1.x). It can edit the
  wrong place, which undercuts the reason for requiring a unique match.

## Consequences

- The code stays small, and an edit is either exactly what the model asked for or an
  error.
- MiMo handled the benchmark's trailing-whitespace trap 5 out of 5 times. Near misses
  cost a retry, guided by the hint.
- CRLF files match because `read_text()` translates line endings, but the write turns
  them into LF (backlog: "Line endings").
