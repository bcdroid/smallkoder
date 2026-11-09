#!/usr/bin/env python3
"""Claude Code PreToolUse hook: don't let tests be weakened quietly.

Claude Code runs this before every Edit or Write, with the tool call as JSON
on stdin. For Python files under a tests/ directory it blocks (exit code 2,
reason on stderr, which Claude Code shows to Claude):

  * adding a skip or xfail marker, and
  * removing or changing an existing `assert` or `pytest.raises` line.

Either is allowed if the new text carries a `# test-guard: <reason>` comment
(on the same line for skips; anywhere in the new text for assertion changes).
The change is still possible, but never silent: the reason shows in the diff.

This catches mistakes; it is not a security boundary. Edits made through
Bash (sed, python -c ...) do not trigger Edit/Write hooks.
"""

import json
import re
import sys
from pathlib import Path

OVERRIDE = "# test-guard:"
SKIP_PATTERN = re.compile(
    r"pytest\.mark\.(skip|skipif|xfail)\b"
    r"|pytest\.(skip|xfail|importorskip)\s*\("
    r"|unittest\.skip|expectedFailure"
)


def assertion_lines(text):
    """The stripped `assert ...` and `pytest.raises(...)` lines in text."""
    lines = (line.strip() for line in text.splitlines())
    return {line for line in lines if line.startswith("assert") or "pytest.raises(" in line}


def problems(old_text, new_text):
    """Reasons to block replacing old_text with new_text (empty list = fine)."""
    found = []
    for line in new_text.splitlines():
        if SKIP_PATTERN.search(line) and OVERRIDE not in line:
            found.append(f"adds a skip/xfail: {line.strip()}")
    if OVERRIDE not in new_text:
        new_lines = {line.strip() for line in new_text.splitlines()}
        for line in sorted(assertion_lines(old_text) - new_lines):
            found.append(f"removes or changes an assertion: {line}")
    return found


def changes(tool_name, tool_input):
    """(old_text, new_text) pairs for this Edit or Write call."""
    if tool_name == "Write":
        path = Path(tool_input["file_path"])
        old = path.read_text() if path.is_file() else ""
        return [(old, tool_input.get("content", ""))]
    edits = tool_input.get("edits") or [tool_input]  # MultiEdit sends a list
    return [(e.get("old_string", ""), e.get("new_string", "")) for e in edits]


def main():
    event = json.load(sys.stdin)
    tool_input = event.get("tool_input", {})
    path = Path(tool_input.get("file_path", ""))
    if "tests" not in path.parts or path.suffix != ".py":
        return 0

    found = []
    for old, new in changes(event.get("tool_name", ""), tool_input):
        found += problems(old, new)
    if not found:
        return 0

    print(f"Blocked edit to {path}: it would weaken the tests.", file=sys.stderr)
    for problem in found:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "Fix the code instead of the test. If the test really is wrong, make the "
        f"change with a '{OVERRIDE} <reason>' comment so it shows up in review, "
        "and say so in the commit message.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
