"""Tests for .claude/hooks/guard_tests.py, the Claude Code hook that stops
tests from being weakened.

We run the hook exactly as Claude Code does: a separate process, JSON on
stdin, and the exit code decides (0 = allow, 2 = block, stderr = reason).
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "guard_tests.py"

# Built from pieces so this file does not trip the guard it is testing.
SKIP_MARK = "@pytest.mark." + "skip"
XFAIL_MARK = "@pytest.mark." + "xfail"
SKIP_CALL = "pytest." + "skip('later')"


def run_hook(tool_name, tool_input):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
    )


def assert_blocked(result):
    # Exit code 2 alone is not enough: Python also exits 2 if the script is missing.
    assert_blocked(result)
    assert "# test-guard:" in result.stderr  # the message explains how to override


def write(path, content):
    return run_hook("Write", {"file_path": str(path), "content": content})


def edit(path, old, new):
    return run_hook("Edit", {"file_path": str(path), "old_string": old, "new_string": new})


def test_allows_ordinary_test_file(tmp_path):
    result = write(tmp_path / "tests" / "test_x.py", "def test_x():\n    assert 1 == 1\n")
    assert result.returncode == 0


def test_ignores_files_outside_tests(tmp_path):
    result = write(tmp_path / "smallkoder" / "x.py", SKIP_MARK + "\n")
    assert result.returncode == 0


def test_blocks_skip_marker(tmp_path):
    result = write(tmp_path / "tests" / "test_x.py", SKIP_MARK + "\ndef test_x():\n    assert False\n")
    assert_blocked(result)
    assert "skip" in result.stderr


def test_blocks_xfail_marker_in_edit(tmp_path):
    result = edit(tmp_path / "tests" / "test_x.py", "def test_x():", XFAIL_MARK + "\ndef test_x():")
    assert_blocked(result)


def test_blocks_skip_call(tmp_path):
    result = edit(tmp_path / "tests" / "test_x.py", "    assert x\n", "    " + SKIP_CALL + "\n    assert x\n")
    assert_blocked(result)


def test_allows_skip_with_reason_comment(tmp_path):
    line = SKIP_MARK + "  # test-guard: needs a real API key\n"
    result = write(tmp_path / "tests" / "test_x.py", line + "def test_x():\n    pass\n")
    assert result.returncode == 0


def test_blocks_edit_that_removes_an_assert(tmp_path):
    result = edit(
        tmp_path / "tests" / "test_x.py",
        "    assert add(2, 2) == 4\n",
        "    add(2, 2)\n",
    )
    assert_blocked(result)
    assert "assert add(2, 2) == 4" in result.stderr


def test_blocks_edit_that_changes_an_assert(tmp_path):
    result = edit(
        tmp_path / "tests" / "test_x.py",
        "    assert add(2, 2) == 4\n",
        "    assert add(2, 2) in (4, 5)\n",
    )
    assert_blocked(result)


def test_allows_assert_change_with_reason_comment(tmp_path):
    result = edit(
        tmp_path / "tests" / "test_x.py",
        "    assert add(2, 2) == 4\n",
        "    assert add(2, 2) == 4.0  # test-guard: add now returns float\n",
    )
    assert result.returncode == 0


def test_allows_adding_asserts(tmp_path):
    result = edit(
        tmp_path / "tests" / "test_x.py",
        "    assert add(2, 2) == 4\n",
        "    assert add(2, 2) == 4\n    assert add(0, 0) == 0\n",
    )
    assert result.returncode == 0


def test_write_over_existing_file_cannot_drop_asserts(tmp_path):
    existing = tmp_path / "tests" / "test_x.py"
    existing.parent.mkdir()
    existing.write_text("def test_x():\n    assert add(2, 2) == 4\n")
    result = write(existing, "def test_x():\n    pass\n")
    assert_blocked(result)
