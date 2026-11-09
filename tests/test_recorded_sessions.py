"""End-to-end tests: replay real recorded sessions through the real code.

Each trace in tests/traces/ was recorded once against the real API by
scripts/record_traces.py. Here the ReplayModel plays the model's part: it
returns the recorded replies and fails if our code sends anything different
from what was recorded. Everything else (the loop, the tools, the files on
disk) runs for real.

If you change the system prompt or tool schemas, these fail on purpose:
re-record with `uv run scripts/record_traces.py`.
"""

import json
import re
from pathlib import Path

import pytest

from smallkoder.agent import new_conversation, run_turn
from smallkoder.traces import ReplayModel, snapshot

TRACE_DIR = Path(__file__).parent / "traces"
TRACES = sorted(TRACE_DIR.glob("*.json"))


def load(name):
    return json.loads((TRACE_DIR / f"{name}.json").read_text())


def replay(trace, workdir):
    """Run the trace's prompts against its recorded replies; return the messages."""
    for name, text in trace["files_before"].items():
        (workdir / name).parent.mkdir(parents=True, exist_ok=True)
        (workdir / name).write_text(text)
    model = ReplayModel(trace["exchanges"])
    approvals = list(trace["approvals"])
    messages = new_conversation()

    def approve(*question):  # writes and commands share one list of answers
        return approvals.pop(0)

    answers = [
        run_turn(model, messages, prompt, workdir, approve, approve_command=approve)
        for prompt in trace["prompts"]
    ]

    assert answers == trace["answers"]
    assert model.finished, "the code made fewer model calls than were recorded"
    assert approvals == [], "the code asked for fewer approvals than were recorded"
    return messages


def tool_results(messages):
    return [m["content"] for m in messages if m["role"] == "tool"]


def test_there_are_traces():
    assert len(TRACES) >= 5


@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.stem)
def test_trace_replays_exactly(path, tmp_path):
    trace = json.loads(path.read_text())
    replay(trace, tmp_path.resolve())
    assert snapshot(tmp_path.resolve()) == trace["files_after"]


@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.stem)
def test_trace_has_no_secrets(path):
    text = path.read_text()
    assert not re.search(r"oc_sk|\bsk-|Bearer|Authorization|x-opencode-session", text)


# --- what each recorded session shows ---


def test_add_docstring(tmp_path):
    replay(load("add_docstring"), tmp_path.resolve())
    hello = (tmp_path / "hello.py").read_text()
    assert '"""' in hello and "def greet(name):" in hello


def test_declined_write_leaves_file_unchanged(tmp_path):
    messages = replay(load("declined_write"), tmp_path.resolve())
    assert (tmp_path / "config.py").read_text() == "DEBUG = False\n"
    assert "Error: the user declined this write" in tool_results(messages)


def test_missing_file_is_an_error_result(tmp_path):
    messages = replay(load("missing_file"), tmp_path.resolve())
    assert "Error: file not found: missing.py" in tool_results(messages)


def test_reading_outside_the_workspace_is_refused(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    (tmp_path / "secret.txt").write_text("TOP SECRET")  # really there, still refused
    messages = replay(load("outside_workspace"), workdir.resolve())
    results = tool_results(messages)
    assert any("outside the working directory" in r for r in results)
    assert not any("TOP SECRET" in r for r in results)


def test_run_program_returns_its_output(tmp_path):
    messages = replay(load("run_program"), tmp_path.resolve())
    assert "Exit code: 0\nHello, world!\n" in tool_results(messages)


def test_declined_command_does_not_run(tmp_path):
    messages = replay(load("declined_command"), tmp_path.resolve())
    assert (tmp_path / "notes.txt").exists()
    assert "Error: the user declined this command" in tool_results(messages)


def test_two_turns_share_one_conversation(tmp_path):
    messages = replay(load("two_turns"), tmp_path.resolve())
    assert [m["content"] for m in messages if m["role"] == "user"] == load("two_turns")["prompts"]
    assert (tmp_path / "greeting.txt").read_text().strip() == "hi there"
