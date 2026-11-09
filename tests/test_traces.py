"""Tests for smallkoder.traces: recording model calls and replaying them."""

import json

import pytest

from smallkoder.agent import new_conversation, run_turn
from smallkoder.model import OpenCodeModel
from smallkoder.traces import RecordingModel, ReplayModel, TraceMismatch, record_session
from tests.fakes import ScriptedModel, answer, tool_calls

KEY = "oc_sk_test_not_a_real_key"


def test_recorder_passes_replies_through_and_remembers_requests():
    recorder = RecordingModel(ScriptedModel([answer("hi")]))
    messages = [{"role": "user", "content": "hello"}]

    assert recorder.complete(messages, []) == answer("hi")
    messages.append({"role": "user", "content": "changed later"})  # must not affect the record

    assert recorder.exchanges == [{
        "request": {"messages": [{"role": "user", "content": "hello"}], "tools": []},
        "response": answer("hi"),
    }]


def test_save_writes_metadata_and_exchanges(tmp_path):
    recorder = RecordingModel(ScriptedModel([answer("hi")]))
    recorder.complete([{"role": "user", "content": "hello"}], [])
    path = tmp_path / "trace.json"

    recorder.save(path, description="says hi", prompts=["hello"])

    data = json.loads(path.read_text())
    assert data["description"] == "says hi"
    assert data["prompts"] == ["hello"]
    assert data["exchanges"] == recorder.exchanges


def test_saved_trace_never_contains_the_key(tmp_path):
    def fake_post(url, headers, body):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    recorder = RecordingModel(OpenCodeModel(KEY, post=fake_post))
    recorder.complete([{"role": "user", "content": "hi"}], [])
    path = tmp_path / "trace.json"
    recorder.save(path)

    text = path.read_text()
    assert KEY not in text
    assert "Authorization" not in text and "Bearer" not in text


def test_replay_serves_recorded_responses_in_order():
    exchanges = [
        {"request": {"messages": [1], "tools": []}, "response": answer("one")},
        {"request": {"messages": [2], "tools": []}, "response": answer("two")},
    ]
    replay = ReplayModel(exchanges)
    assert not replay.finished
    assert replay.complete([1], []) == answer("one")
    assert replay.complete([2], []) == answer("two")
    assert replay.finished


def test_replay_rejects_a_different_request():
    replay = ReplayModel([{"request": {"messages": [{"role": "user", "content": "a"}], "tools": []},
                           "response": answer("x")}])
    with pytest.raises(TraceMismatch, match="request 1 differs"):
        replay.complete([{"role": "user", "content": "b"}], [])


def test_replay_rejects_different_tools():
    replay = ReplayModel([{"request": {"messages": [], "tools": [{"name": "a"}]}, "response": answer("x")}])
    with pytest.raises(TraceMismatch, match="tools"):
        replay.complete([], [{"name": "b"}])


def test_replay_rejects_extra_requests():
    replay = ReplayModel([])
    with pytest.raises(TraceMismatch, match="no more recorded responses"):
        replay.complete([], [])


def test_replay_returns_copies():
    replay = ReplayModel([{"request": {"messages": [], "tools": []}, "response": answer("x")}])
    reply = replay.complete([], [])
    reply["content"] = "mutated"
    assert replay.exchanges[0]["response"] == answer("x")


def test_record_session_runs_prompts_in_a_workspace(tmp_path):
    workdir = tmp_path.resolve()
    model = ScriptedModel([
        tool_calls(("read_file", {"path": "a.txt"})),
        answer("It says A."),
        tool_calls(("write_file", {"path": "a.txt", "content": "B\n"})),
        answer("Changed it."),
    ])

    trace = record_session(model, {"a.txt": "A\n"}, ["read a.txt", "change it to B"], [True], workdir)

    assert trace["files_before"] == {"a.txt": "A\n"}
    assert trace["prompts"] == ["read a.txt", "change it to B"]
    assert trace["answers"] == ["It says A.", "Changed it."]
    assert trace["approvals"] == [True]
    assert trace["files_after"] == {"a.txt": "B\n"}
    assert len(trace["exchanges"]) == 4


def test_record_session_shares_approvals_between_writes_and_commands(tmp_path):
    workdir = tmp_path.resolve()
    model = ScriptedModel([
        tool_calls(("run_command", {"command": "echo hi"})),
        tool_calls(("write_file", {"path": "a.txt", "content": "A\n"})),
        answer("Done."),
    ])
    trace = record_session(model, {}, ["go"], [True, False], workdir)
    assert trace["approvals"] == [True, False]
    assert trace["files_after"] == {}
    assert trace["exchanges"][1]["request"]["messages"][-1]["content"] == "Exit code: 0\nhi\n"


def test_record_session_records_approvals_actually_used(tmp_path):
    model = ScriptedModel([answer("Nothing to write.")])
    trace = record_session(model, {}, ["hi"], [True, False], tmp_path.resolve())
    assert trace["approvals"] == []


def test_record_then_replay_a_whole_turn(tmp_path):
    root = tmp_path.resolve()
    (root / "a.txt").write_text("A\n")
    script = [tool_calls(("read_file", {"path": "a.txt"})), answer("It says A.")]

    recorder = RecordingModel(ScriptedModel(script))
    recorded = new_conversation()
    run_turn(recorder, recorded, "read a.txt", root, lambda *a: True)

    replay = ReplayModel(recorder.exchanges)
    replayed = new_conversation()
    run_turn(replay, replayed, "read a.txt", root, lambda *a: True)

    assert replayed == recorded
    assert replay.finished
