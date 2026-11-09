"""Tests for the interactive command line, with fake input and a fake model."""

import pytest

from smallkoder.cli import main, make_diff, repl
from smallkoder.model import ModelError
from tests.fakes import ScriptedModel, answer, scripted_input, tool_calls


@pytest.fixture
def root(tmp_path):
    return tmp_path.resolve()


def run(model, root, *lines):
    """Run the REPL with the given input lines; return everything printed."""
    output = []
    repl(model, root, input=scripted_input(*lines), output=output.append)
    return "\n".join(output)


def test_prints_the_answer_and_stops_at_eof(root):
    printed = run(ScriptedModel([answer("Hello there!")]), root, "hi")
    assert "Hello there!" in printed


@pytest.mark.parametrize("command", ["exit", "quit", " EXIT "])
def test_exit_commands(root, command):
    model = ScriptedModel([])
    run(model, root, command, "this line is never read")
    assert model.requests == []


def test_blank_lines_are_ignored(root):
    model = ScriptedModel([answer("ok")])
    run(model, root, "", "   ", "hi")
    assert len(model.requests) == 1


def test_tool_calls_are_shown(root):
    (root / "hello.py").write_text("x = 1\n")
    model = ScriptedModel([tool_calls(("read_file", {"path": "hello.py"})), answer("ok")])
    printed = run(model, root, "read it")
    assert '[read_file] {"path": "hello.py"}' in printed


def test_long_tool_arguments_are_shortened(root):
    content = "x = 1\n" * 100
    model = ScriptedModel([tool_calls(("write_file", {"path": "a.py", "content": content})), answer("ok")])
    printed = run(model, root, "write", "n")
    line = next(line for line in printed.splitlines() if "[write_file]" in line)
    assert len(line) < 100 and line.endswith("...")


def test_write_shows_diff_and_asks(root):
    (root / "hello.py").write_text("def greet():\n    pass\n")
    new = 'def greet():\n    """Say hi."""\n    pass\n'
    model = ScriptedModel([tool_calls(("write_file", {"path": "hello.py", "content": new})), answer("Done.")])
    fake_input = scripted_input("add a docstring", "y")
    output = []

    repl(model, root, input=fake_input, output=output.append)

    printed = "\n".join(output)
    assert '+    """Say hi."""' in printed
    assert "Allow this write? [y/N]" in fake_input.prompts[1]
    assert (root / "hello.py").read_text() == new


@pytest.mark.parametrize("reply", ["n", "", "maybe", "no"])
def test_anything_but_yes_declines(root, reply):
    model = ScriptedModel([tool_calls(("write_file", {"path": "a.py", "content": "x\n"})), answer("ok")])
    run(model, root, "write a.py", reply)
    assert not (root / "a.py").exists()


def test_eof_at_approval_prompt_declines(root):
    model = ScriptedModel([tool_calls(("write_file", {"path": "a.py", "content": "x\n"})), answer("ok")])
    run(model, root, "write a.py")  # input ends before the approval question
    assert not (root / "a.py").exists()


def test_api_error_is_shown_and_conversation_rolled_back(root):
    model = ScriptedModel([ModelError("HTTP 500: server sad"), answer("Second try worked.")])
    printed = run(model, root, "first", "second")

    assert "HTTP 500: server sad" in printed
    assert "Second try worked." in printed
    roles_and_text = [(m["role"], m.get("content")) for m in model.requests[1][0]]
    assert ("user", "first") not in roles_and_text
    assert roles_and_text[-1] == ("user", "second")


def test_ctrl_c_quits(root):
    def interrupted(prompt=""):
        raise KeyboardInterrupt

    output = []
    repl(ScriptedModel([]), root, input=interrupted, output=output.append)  # returns, no traceback


def test_make_diff_for_new_file():
    diff = make_diff("new.py", None, "x = 1\n")
    assert "+++ new.py" in diff and "+x = 1" in diff


def test_main_without_key_exits_with_message(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENCODE_GO", raising=False)
    assert main([]) == 1
    assert "OPENCODE_GO" in capsys.readouterr().err
