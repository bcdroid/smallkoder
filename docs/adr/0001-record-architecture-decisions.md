# 0001. Record decisions as ADRs, and write a spec for each feature

- **Status:** Accepted
- **Date:** 2026-11-11

## Context

v0.1 was designed in one document, [`docs/plan.md`](../plan.md), kept as written, with a
"What changed during implementation" list for departures. That worked for one
up-front design. It works less well for features added later from the backlog.

The `run_command` tool (2026-11-09) is an example. Its design decisions ended up spread
across commit messages, the README's guardrails section and one long bullet in plan.md.
To learn why commands aren't checked for `.env`, a reader had to find the right commit.
Some decisions were the user's (approval policy, guardrail stance, re-recording traces)
and were made in conversation, so they weren't recorded anywhere.

## Decision

- Each new feature gets a spec in `docs/specs/<feature>.md`: goal, non-goals,
  interface, behaviour, errors, guardrails, tests, known gaps.
- Each decision with real alternatives gets an ADR in `docs/adr/NNNN-<slug>.md`, listed
  in [`docs/adr/README.md`](README.md).
- Both are written **before** the code and committed before or with the red tests. They
  are updated when implementation changes the plan.
- `docs/plan.md` stays the v0.1 design, unchanged apart from its "What changed" list.

The `run_command` spec and ADRs 0002–0006 were written after the code, as a catch-up.
They say so.

## Alternatives considered

- **Keep extending plan.md.** One growing file mixes the original design with every later
  feature, and CLAUDE.md asks to keep its text as written.
- **Commit messages only.** They hold the reasons, but they are hard to find and can't be
  updated when a decision changes.
- **A spec without ADRs.** A spec says what was built, not what was rejected and why;
  that is the part people forget, and the part a teaching repo most needs.

## Consequences

- Before the code there is a short design step. When a decision is genuinely the
  user's, it gets asked and then written down in an ADR.
- Reviewers can check the code against a spec.
- Changing a decision means a new ADR that supersedes the old one, not an edit.
