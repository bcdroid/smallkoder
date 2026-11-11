"""Tests for smallkoder.tools: the two tools and their guardrails."""

import pytest

import os
import signal
import time

from smallkoder.tools import TOOLS, ToolError, keep_end, read_file, resolve_path, run_command, run_tool, write_file


@pytest.fixture
def root(tmp_path):
    """A workspace directory, resolved (tmp_path may sit behind a symlink)."""
    workspace = tmp_path / "work"
    workspace.mkdir()
    return workspace.resolve()


# --- resolve_path: confining paths to the working directory ---


def test_resolve_relative_path_inside_root(root):
    assert resolve_path(root, "src/app.py") == root / "src" / "app.py"


def test_resolve_allows_dotdot_that_stays_inside(root):
    assert resolve_path(root, "src/../app.py") == root / "app.py"


def test_resolve_refuses_parent_directory(root):
    with pytest.raises(ToolError, match="outside the working directory"):
        resolve_path(root, "../secret.txt")


def test_resolve_refuses_absolute_path_outside(root):
    with pytest.raises(ToolError, match="outside the working directory"):
        resolve_path(root, "/etc/passwd")


def test_resolve_refuses_symlink_pointing_outside(root, tmp_path):
    (tmp_path / "outside.txt").write_text("secret")
    (root / "link.txt").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(ToolError, match="outside the working directory"):
        resolve_path(root, "link.txt")


def test_resolve_refuses_env_files(root):
    with pytest.raises(ToolError, match="secret file"):
        resolve_path(root, ".env")
    with pytest.raises(ToolError, match="secret file"):
        resolve_path(root, "config/.env")


# --- read_file ---


def test_read_file_returns_contents(root):
    (root / "hello.py").write_text("print('hi')\n")
    assert read_file(root, "hello.py") == "print('hi')\n"


def test_read_file_missing(root):
    with pytest.raises(ToolError, match="file not found: nope.py"):
        read_file(root, "nope.py")


def test_read_file_directory(root):
    (root / "src").mkdir()
    with pytest.raises(ToolError, match="is a directory"):
        read_file(root, "src")


def test_read_file_not_text(root):
    (root / "image.bin").write_bytes(b"\xff\xfe\x00\x81")
    with pytest.raises(ToolError, match="not a UTF-8 text file"):
        read_file(root, "image.bin")


# --- write_file: needs approval ---


def always(answer):
    """An approver that records what it was asked and always answers `answer`."""

    def approve(path, old_text, new_text):
        approve.calls.append((path, old_text, new_text))
        return answer

    approve.calls = []
    return approve


def test_write_file_creates_new_file_when_approved(root):
    approve = always(True)
    result = write_file(root, "hello.py", "print('hi')\n", approve)
    assert (root / "hello.py").read_text() == "print('hi')\n"
    assert result == "Wrote 1 lines to hello.py"
    assert approve.calls == [("hello.py", None, "print('hi')\n")]  # None: new file


def test_write_file_replaces_whole_file(root):
    (root / "hello.py").write_text("old\ntext\n")
    approve = always(True)
    write_file(root, "hello.py", "new\n", approve)
    assert (root / "hello.py").read_text() == "new\n"
    assert approve.calls == [("hello.py", "old\ntext\n", "new\n")]


def test_write_file_creates_parent_directories(root):
    write_file(root, "src/pkg/mod.py", "x = 1\n", always(True))
    assert (root / "src" / "pkg" / "mod.py").read_text() == "x = 1\n"


def test_write_file_declined_leaves_file_alone(root):
    (root / "hello.py").write_text("old\n")
    with pytest.raises(ToolError, match="user declined"):
        write_file(root, "hello.py", "new\n", always(False))
    assert (root / "hello.py").read_text() == "old\n"


def test_write_file_outside_root_is_refused_without_asking(root, tmp_path):
    approve = always(True)
    with pytest.raises(ToolError, match="outside the working directory"):
        write_file(root, "../escape.txt", "boo\n", approve)
    assert not (tmp_path / "escape.txt").exists()
    assert approve.calls == []


def test_write_file_refuses_env(root):
    with pytest.raises(ToolError, match="secret file"):
        write_file(root, ".env", "OPENCODE_GO=stolen\n", always(True))


def test_write_file_onto_directory(root):
    (root / "src").mkdir()
    with pytest.raises(ToolError, match="is a directory"):
        write_file(root, "src", "x\n", always(True))


# --- TOOLS: the JSON schemas sent to the model ---


def test_tools_are_exactly_read_write_and_run_command():
    names = [tool["function"]["name"] for tool in TOOLS]
    # test-guard: the bash tool adds run_command to the tool list on purpose
    assert names == ["read_file", "write_file", "run_command"]


def test_tool_schemas_follow_strict_rules():
    for tool in TOOLS:
        assert tool["type"] == "function"
        assert tool["function"]["description"]
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        assert sorted(params["required"]) == sorted(params["properties"])


# --- run_tool: arguments arrive as a JSON string; errors become text ---


def test_run_tool_read(root):
    (root / "a.txt").write_text("hello\n")
    assert run_tool("read_file", '{"path": "a.txt"}', root, always(True)) == "hello\n"


def test_run_tool_write(root):
    result = run_tool("write_file", '{"path": "a.txt", "content": "hi\\n"}', root, always(True))
    assert result == "Wrote 1 lines to a.txt"
    assert (root / "a.txt").read_text() == "hi\n"


def test_run_tool_reports_tool_errors_as_text(root):
    assert run_tool("read_file", '{"path": "nope.txt"}', root, always(True)) == "Error: file not found: nope.txt"


def test_run_tool_unknown_tool(root):
    result = run_tool("delete_file", '{"path": "a.txt"}', root, always(True))
    # test-guard: run_command is now one of the available tools
    assert result == "Error: unknown tool 'delete_file'. Available tools: read_file, write_file, run_command"


@pytest.mark.parametrize("arguments", ['{"path": ', "not json", "[1, 2]", '"a.txt"', ""])
def test_run_tool_arguments_not_a_json_object(root, arguments):
    result = run_tool("read_file", arguments, root, always(True))
    assert result.startswith("Error: arguments must be a JSON object")


def test_run_tool_missing_argument(root):
    result = run_tool("write_file", '{"path": "a.txt"}', root, always(True))
    assert result == "Error: write_file needs string arguments 'path', 'content'"


def test_run_tool_wrong_argument_type(root):
    result = run_tool("read_file", '{"path": 42}', root, always(True))
    assert result == "Error: read_file needs string arguments 'path'"


def test_run_tool_unexpected_argument(root):
    result = run_tool("read_file", '{"path": "a.txt", "lines": 10}', root, always(True))
    assert result == "Error: read_file got unexpected arguments 'lines'"


# --- run_command: a shell command, approved first ---


def allow(answer):
    """A command approver that records the commands it was asked about."""

    def approve_command(command):
        approve_command.calls.append(command)
        return answer

    approve_command.calls = []
    return approve_command


def test_run_command_returns_exit_code_and_output(root):
    approve = allow(True)
    assert run_command(root, "echo hello", approve) == "Exit code: 0\nhello\n"
    assert approve.calls == ["echo hello"]


def test_run_command_runs_in_the_working_directory(root):
    (root / "here.txt").write_text("")
    assert run_command(root, "ls", allow(True)) == "Exit code: 0\nhere.txt\n"


def test_run_command_merges_stderr_and_reports_failure(root):
    result = run_command(root, "echo out; echo err >&2; exit 3", allow(True))
    assert result == "Exit code: 3\nout\nerr\n"


def test_run_command_uses_bash(root):
    assert run_command(root, "echo $((6 * 7))", allow(True)) == "Exit code: 0\n42\n"


def test_run_command_declined_does_not_run(root):
    with pytest.raises(ToolError, match="the user declined this command"):
        run_command(root, "touch made.txt", allow(False))
    assert not (root / "made.txt").exists()


def test_run_command_refuses_empty_command_without_asking(root):
    approve = allow(True)
    with pytest.raises(ToolError, match="command is empty"):
        run_command(root, "   ", approve)
    assert approve.calls == []


def test_run_command_hides_the_api_key(root, monkeypatch):
    monkeypatch.setenv("OPENCODE_GO", "not-a-real-key")
    assert run_command(root, 'echo "key=$OPENCODE_GO"', allow(True)) == "Exit code: 0\nkey=\n"


def test_run_command_without_bash_is_a_tool_error(root, tmp_path, monkeypatch):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))  # Popen looks bash up on this PATH
    with pytest.raises(ToolError, match="could not start bash: .*No such file or directory: 'bash'"):
        run_command(root, "echo hi", allow(True))


def test_run_tool_without_bash_reports_an_error(root, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    result = run_tool("run_command", '{"command": "echo hi"}', root, always(True), approve_command=allow(True))
    assert result.startswith("Error: could not start bash: ")


def test_run_command_cannot_read_input(root):
    # stdin is closed, so a command waiting for input gets EOF instead of hanging.
    assert run_command(root, "cat", allow(True), timeout=5) == "Exit code: 0\n"


def test_run_command_times_out_and_keeps_partial_output(root):
    with pytest.raises(ToolError, match=r"timed out after 0.5 s(.|\n)*started"):
        run_command(root, "echo started; sleep 30", allow(True), timeout=0.5)


def test_run_command_timeout_kills_background_children(root):
    # A background child keeps the output pipe open. Killing only bash would
    # leave us waiting for it; the whole process group must go.
    start = time.monotonic()
    with pytest.raises(ToolError, match="timed out"):
        run_command(root, "sleep 30 & echo started", allow(True), timeout=0.5)
    assert time.monotonic() - start < 5


def test_run_command_ctrl_c_kills_the_command(root):
    """Ctrl-C reaches smallkoder, not the command (it has its own session),
    so run_command must kill the command before letting the interrupt through."""

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    old_handler = signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, 0.5)
    try:
        with pytest.raises(KeyboardInterrupt):
            run_command(root, "echo $$ > pgid.txt; sleep 30", allow(True), timeout=10)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)

    group = int((root / "pgid.txt").read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(group, 0)  # signal 0: only checks whether the group exists
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("the command's process group was still running after Ctrl-C")


def test_keep_end_leaves_short_text_alone():
    assert keep_end("short", limit=10) == "short"


def test_keep_end_keeps_the_end_of_long_text():
    assert keep_end("abcdefghij", limit=4) == "[... 6 characters cut ...]\nghij"


def test_run_command_output_is_limited(root):
    result = run_command(root, "seq 1 100000", allow(True))
    assert result.startswith("Exit code: 0\n[... ")
    assert result.endswith("99999\n100000\n")
    assert len(result) < 11_000


def test_run_tool_run_command(root):
    result = run_tool("run_command", '{"command": "echo hi"}', root, always(True), approve_command=allow(True))
    assert result == "Exit code: 0\nhi\n"


def test_run_tool_refuses_commands_when_no_approver_is_given(root):
    result = run_tool("run_command", '{"command": "touch made.txt"}', root, always(True))
    assert result == "Error: the user declined this command"
    assert not (root / "made.txt").exists()
