#!/bin/sh
# Claude Code PostToolUse hook: run the test suite after every Edit or Write.
#
# Exit code 2 sends stderr back to Claude, so a failing test shows up
# straight away, while Claude is still looking at the change that broke it.
# (Exit code 1 would only reach the debug log.) Passing runs stay silent.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
# uv runs pytest from the project environment (uv.lock), syncing it first if needed.
if output=$(uv run pytest -q -x 2>&1); then
    exit 0
fi
echo "pytest failed after this edit:" >&2
echo "$output" | tail -n 25 >&2
exit 2
