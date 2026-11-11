"""Tests for the agent loop, using scripted fake models."""

import pytest

from smallkoder.agent import SYSTEM_PROMPT, new_conversation, run_turn
from smallkoder.tools import TOOLS
from tests.fakes import EndlessToolModel, ScriptedModel, answer, tool_calls


@pytest.fixture
def root(tmp_path):
    return tmp_path.resolve()


def yes(path, old_text, new_text):
    return True


def no(path, old_text, new_text):
    return False


def test_new_conversation_starts_with_system_prompt():
    assert new_conversation() == [{"role": "system", "content": SYSTEM_PROMPT}]


def test_system_prompt_names_the_tools_and_no_absolute_paths():
    assert "read_file" in SYSTEM_PROMPT and "write_file" in SYSTEM_PROMPT
    assert "/" not in SYSTEM_PROMPT  # keeps recorded traces portable


def test_system_prompt_mentions_edit_file():
    assert "edit_file" in SYSTEM_PROMPT


def test_edit_file_round_trip(root):
    (root / "calc.py").write_text("x = 1\ny = 2\n")
    edit = {"path": "calc.py", "old_text": "y = 2", "new_text": "y = 3", "replace_all": False}
    model = ScriptedModel([tool_calls(("edit_file", edit)), answer("Changed y.")])
    messages = new_conversation()
    assert run_turn(model, messages, "set y to 3", root, yes) == "Changed y."
    assert (root / "calc.py").read_text() == "x = 1\ny = 3\n"
    assert messages[3]["content"] == "Edited calc.py: replaced 1 occurrence"


def test_plain_answer_ends_the_turn(root):
    model = ScriptedModel([answer("Hello!")])
    messages = new_conversation()

    assert run_turn(model, messages, "hi", root, yes) == "Hello!"
    assert messages[1:] == [{"role": "user", "content": "hi"}, answer("Hello!")]
    sent_messages, sent_tools = model.requests[0]
    assert sent_messages == messages[:2]
    assert sent_tools == TOOLS


def test_tool_call_then_answer(root):
    (root / "hello.py").write_text("print('hi')\n")
    model = ScriptedModel([tool_calls(("read_file", {"path": "hello.py"})), answer("It prints hi.")])
    messages = new_conversation()

    assert run_turn(model, messages, "what is in hello.py?", root, yes) == "It prints hi."
    tool_result = {"role": "tool", "tool_call_id": "call_1", "content": "print('hi')\n"}
    assert messages[3] == tool_result
    # The second request carries the tool result back to the model.
    assert model.requests[1][0][-1] == tool_result


def test_several_tool_calls_in_one_reply(root):
    (root / "a.txt").write_text("A")
    (root / "b.txt").write_text("B")
    model = ScriptedModel([
        tool_calls(("read_file", {"path": "a.txt"}), ("read_file", {"path": "b.txt"})),
        answer("done"),
    ])
    messages = new_conversation()
    run_turn(model, messages, "read both", root, yes)

    results = [(m["tool_call_id"], m["content"]) for m in messages if m["role"] == "tool"]
    assert results == [("call_1", "A"), ("call_2", "B")]


def test_write_is_approved_then_done(root):
    model = ScriptedModel([
        tool_calls(("write_file", {"path": "new.py", "content": "x = 1\n"})),
        answer("Created new.py."),
    ])
    run_turn(model, new_conversation(), "make new.py", root, yes)
    assert (root / "new.py").read_text() == "x = 1\n"


def test_declined_write_is_reported_to_the_model(root):
    model = ScriptedModel([
        tool_calls(("write_file", {"path": "new.py", "content": "x = 1\n"})),
        answer("OK, I won't."),
    ])
    messages = new_conversation()
    assert run_turn(model, messages, "make new.py", root, no) == "OK, I won't."
    assert not (root / "new.py").exists()
    assert messages[3]["content"] == "Error: the user declined this write"


def test_on_tool_callback_sees_each_call(root):
    seen = []
    model = ScriptedModel([tool_calls(("read_file", {"path": "x"})), answer("ok")])
    run_turn(model, new_conversation(), "go", root, yes, on_tool=lambda name, args: seen.append((name, args)))
    # test-guard: on_tool gets the raw JSON string, so the CLI shows exactly what the model sent
    assert seen == [("read_file", '{"path": "x"}')]


def test_missing_content_in_final_answer_becomes_empty_string(root):
    model = ScriptedModel([{"role": "assistant", "content": None}])
    assert run_turn(model, new_conversation(), "hi", root, yes) == ""


def test_conversation_continues_across_turns(root):
    model = ScriptedModel([answer("one"), answer("two")])
    messages = new_conversation()
    run_turn(model, messages, "first", root, yes)
    run_turn(model, messages, "second", root, yes)
    assert [m["role"] for m in model.requests[1][0]] == ["system", "user", "assistant", "user"]


# --- fault injection: the model misbehaves, the loop survives ---


@pytest.mark.parametrize(
    "bad_call, expected_error",
    [
        (("read_file", '{"path": "a.txt"'), "Error: arguments must be a JSON object"),
        (("rm_rf", {"path": "/"}), "Error: unknown tool 'rm_rf'"),
        (("write_file", {"path": "a.txt"}), "Error: write_file needs string arguments"),
        (("read_file", {"path": "../../etc/passwd"}), "Error: path '../../etc/passwd' is outside"),
    ],
)
def test_bad_tool_calls_become_error_results(root, bad_call, expected_error):
    model = ScriptedModel([tool_calls(bad_call), answer("sorry")])
    messages = new_conversation()
    assert run_turn(model, messages, "go", root, yes) == "sorry"
    assert messages[3]["role"] == "tool"
    assert messages[3]["content"].startswith(expected_error)


def test_step_limit_stops_a_model_that_never_finishes(root):
    model = EndlessToolModel()
    result = run_turn(model, new_conversation(), "go", root, yes, max_steps=5)
    assert model.calls == 5
    assert "stopped" in result
