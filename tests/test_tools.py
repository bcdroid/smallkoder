"""Tests for smallkoder.tools: the tools and their guardrails."""

import json

import pytest

from smallkoder.tools import TOOLS, ToolError, edit_file, read_file, resolve_path, run_tool, write_file


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


# --- edit_file: replace exact text, which must be unique unless replace_all ---

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"


@pytest.fixture
def calc(root):
    (root / "calc.py").write_text(CALC)
    return root / "calc.py"


def test_edit_file_replaces_unique_text(root, calc):
    approve = always(True)
    result = edit_file(root, "calc.py", "return a - b", "return b - a", False, approve)
    assert calc.read_text() == CALC.replace("return a - b", "return b - a")
    assert result == "Edited calc.py: replaced 1 occurrence"
    assert approve.calls == [("calc.py", CALC, calc.read_text())]  # whole files, so the CLI can diff


def test_edit_file_can_span_lines(root, calc):
    edit_file(root, "calc.py", "def add(a, b):\n    return a + b", "def add(a, b):\n    return b + a", False, always(True))
    assert calc.read_text().startswith("def add(a, b):\n    return b + a\n")


def test_edit_file_new_text_can_be_empty_to_delete(root, calc):
    edit_file(root, "calc.py", "\n\ndef sub(a, b):\n    return a - b\n", "", False, always(True))
    assert calc.read_text() == "def add(a, b):\n    return a + b\n"


def test_edit_file_not_found(root, calc):
    with pytest.raises(ToolError, match="old_text not found in calc.py. It must match the file exactly"):
        edit_file(root, "calc.py", "return a * b", "x", False, always(True))
    assert calc.read_text() == CALC


def test_edit_file_not_found_hints_at_whitespace(root, calc):
    with pytest.raises(ToolError, match="would match if spaces at the ends of lines were ignored"):
        edit_file(root, "calc.py", "def add(a, b):  \n    return a + b", "x", False, always(True))


def test_edit_file_crlf_file_matches_lf_text(root):
    # read_text() turns \r\n into \n, so the model only ever sees \n, and the
    # write turns the whole file into \n line endings (as write_file does).
    # test-guard: my first version expected an error, but Python's newline translation makes CRLF files match
    (root / "win.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    edit_file(root, "win.py", "x = 1\ny = 2", "x = 3", False, always(True))
    assert (root / "win.py").read_bytes() == b"x = 3\n"


def test_edit_file_ambiguous_says_how_many_and_where(root, calc):
    approve = always(True)
    with pytest.raises(ToolError) as error:
        edit_file(root, "calc.py", "(a, b):", "(x, y):", False, approve)
    assert str(error.value) == (
        "old_text appears 2 times in calc.py (lines 1, 5). Include more surrounding lines "
        "so it matches only once, or set replace_all to true to change every one."
    )
    assert calc.read_text() == CALC
    assert approve.calls == []  # refused before asking the user


def test_edit_file_replace_all(root, calc):
    result = edit_file(root, "calc.py", "(a, b):", "(x, y):", True, always(True))
    assert calc.read_text().count("(x, y):") == 2
    assert result == "Edited calc.py: replaced 2 occurrences"


def test_edit_file_replace_all_with_one_match(root, calc):
    assert edit_file(root, "calc.py", "a + b", "b + a", True, always(True)) == "Edited calc.py: replaced 1 occurrence"


def test_edit_file_empty_old_text(root, calc):
    with pytest.raises(ToolError, match="old_text is empty. To create a file, use write_file"):
        edit_file(root, "calc.py", "", "x", False, always(True))


def test_edit_file_no_change(root, calc):
    with pytest.raises(ToolError, match="old_text and new_text are the same"):
        edit_file(root, "calc.py", "a + b", "a + b", False, always(True))


def test_edit_file_missing_file(root):
    with pytest.raises(ToolError, match="file not found: nope.py"):
        edit_file(root, "nope.py", "a", "b", False, always(True))


def test_edit_file_declined_leaves_file_alone(root, calc):
    with pytest.raises(ToolError, match="user declined this write"):
        edit_file(root, "calc.py", "a + b", "b + a", False, always(False))
    assert calc.read_text() == CALC


def test_edit_file_outside_root_is_refused_without_asking(root, tmp_path):
    (tmp_path / "outside.py").write_text("x = 1\n")
    approve = always(True)
    with pytest.raises(ToolError, match="outside the working directory"):
        edit_file(root, "../outside.py", "x = 1", "x = 2", False, approve)
    assert (tmp_path / "outside.py").read_text() == "x = 1\n"
    assert approve.calls == []


def test_edit_file_refuses_env(root):
    (root / ".env").write_text("OPENCODE_GO=secret\n")
    with pytest.raises(ToolError, match="secret file"):
        edit_file(root, ".env", "secret", "stolen", False, always(True))


# --- TOOLS: the JSON schemas sent to the model ---


def test_tools_are_exactly_read_write_and_edit():
    names = [tool["function"]["name"] for tool in TOOLS]
    assert names == ["read_file", "write_file", "edit_file"]  # test-guard: edit_file added as a third tool


def test_edit_file_schema():
    (edit,) = [tool["function"] for tool in TOOLS if tool["function"]["name"] == "edit_file"]
    properties = edit["parameters"]["properties"]
    assert {name: spec["type"] for name, spec in properties.items()} == {
        "path": "string",
        "old_text": "string",
        "new_text": "string",
        "replace_all": "boolean",
    }
    assert all(spec["description"] for spec in properties.values())
    assert "exactly once" in edit["description"]
    assert edit["parameters"]["required"] == ["path", "old_text", "new_text"]  # replace_all is optional


def test_tool_schemas_require_every_string_argument():
    # test-guard: replace_all became optional (MiMo left it out in 2 of 3 recorded edits), so only strings are required
    for tool in TOOLS:
        assert tool["type"] == "function"
        assert tool["function"]["description"]
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        strings = [name for name, spec in params["properties"].items() if spec["type"] == "string"]
        assert params["required"] == strings


# --- run_tool: arguments arrive as a JSON string; errors become text ---


def test_run_tool_read(root):
    (root / "a.txt").write_text("hello\n")
    assert run_tool("read_file", '{"path": "a.txt"}', root, always(True)) == "hello\n"


def test_run_tool_write(root):
    result = run_tool("write_file", '{"path": "a.txt", "content": "hi\\n"}', root, always(True))
    assert result == "Wrote 1 lines to a.txt"
    assert (root / "a.txt").read_text() == "hi\n"


def edit_args(**overrides):
    args = {"path": "a.txt", "old_text": "hi", "new_text": "bye", "replace_all": False}
    return json.dumps(args | overrides)


def test_run_tool_edit(root):
    (root / "a.txt").write_text("hi\n")
    assert run_tool("edit_file", edit_args(), root, always(True)) == "Edited a.txt: replaced 1 occurrence"
    assert (root / "a.txt").read_text() == "bye\n"


def test_run_tool_edit_replace_all(root):
    (root / "a.txt").write_text("hi hi\n")
    result = run_tool("edit_file", edit_args(replace_all=True), root, always(True))
    assert result == "Edited a.txt: replaced 2 occurrences"


def test_run_tool_edit_replace_all_defaults_to_false(root):
    # test-guard: replace_all became optional (MiMo left it out in 2 of 3 recorded edits)
    (root / "a.txt").write_text("hi\n")
    arguments = json.dumps({"path": "a.txt", "old_text": "hi", "new_text": "bye"})
    assert run_tool("edit_file", arguments, root, always(True)) == "Edited a.txt: replaced 1 occurrence"
    assert (root / "a.txt").read_text() == "bye\n"


def test_run_tool_edit_without_replace_all_still_refuses_duplicates(root):
    (root / "a.txt").write_text("hi hi\n")
    arguments = json.dumps({"path": "a.txt", "old_text": "hi", "new_text": "bye"})
    result = run_tool("edit_file", arguments, root, always(True))
    assert result.startswith("Error: old_text appears 2 times in a.txt")


def test_run_tool_edit_missing_string_argument(root):
    arguments = json.dumps({"path": "a.txt", "old_text": "hi"})
    result = run_tool("edit_file", arguments, root, always(True))
    assert result == (
        "Error: edit_file needs string arguments 'path', 'old_text', 'new_text' "
        "(and optionally true/false 'replace_all')"
    )


@pytest.mark.parametrize("bad", ["false", 0, None])
def test_run_tool_edit_replace_all_must_be_boolean(root, bad):
    result = run_tool("edit_file", edit_args(replace_all=bad), root, always(True))
    assert result.startswith("Error: edit_file needs string arguments")


def test_run_tool_edit_old_text_must_be_string(root):
    result = run_tool("edit_file", edit_args(old_text=True), root, always(True))
    assert result.startswith("Error: edit_file needs string arguments")


def test_run_tool_reports_tool_errors_as_text(root):
    assert run_tool("read_file", '{"path": "nope.txt"}', root, always(True)) == "Error: file not found: nope.txt"


def test_run_tool_unknown_tool(root):
    result = run_tool("delete_file", '{"path": "a.txt"}', root, always(True))
    assert result == "Error: unknown tool 'delete_file'. Available tools: read_file, write_file, edit_file"  # test-guard: edit_file added as a third tool


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
