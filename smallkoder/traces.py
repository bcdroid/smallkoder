"""Record real model calls to a JSON file, and replay them in tests.

A trace is a list of exchanges: {"request": {"messages", "tools"}, "response"}.
Only messages and tools are recorded. The API key and headers never reach
complete(), so they cannot end up in a trace.
"""

import copy
import json
from pathlib import Path

from smallkoder.agent import new_conversation, run_turn


class TraceMismatch(AssertionError):
    """The code sent something different from what was recorded."""


class RecordingModel:
    """Wraps a real model and remembers every request and response."""

    def __init__(self, model):
        self.model = model
        self.exchanges = []

    def complete(self, messages, tools):
        response = self.model.complete(messages, tools)
        self.exchanges.append({
            "request": {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)},
            "response": copy.deepcopy(response),
        })
        return response

    def save(self, path: Path, **metadata):
        data = {**metadata, "exchanges": self.exchanges}
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


class ReplayModel:
    """Serves recorded responses back, checking each request matches."""

    def __init__(self, exchanges):
        self.exchanges = exchanges
        self.position = 0

    @property
    def finished(self):
        return self.position == len(self.exchanges)

    def complete(self, messages, tools):
        if self.finished:
            raise TraceMismatch(f"request {self.position + 1}: the trace has no more recorded responses")
        exchange = self.exchanges[self.position]
        self.position += 1
        recorded = exchange["request"]
        if tools != recorded["tools"]:
            raise TraceMismatch(f"request {self.position} sent different tools than recorded")
        if messages != recorded["messages"]:
            difference = first_difference(recorded["messages"], messages)
            raise TraceMismatch(f"request {self.position} differs from the trace:\n{difference}")
        return copy.deepcopy(exchange["response"])


def snapshot(workdir: Path) -> dict[str, str]:
    """Every file under workdir, as {relative path: text}."""
    return {
        path.relative_to(workdir).as_posix(): path.read_text()
        for path in sorted(workdir.rglob("*"))
        if path.is_file()
    }


def record_session(model, files, prompts, approvals, workdir: Path) -> dict:
    """Run prompts through the agent in workdir and return the whole trace.

    files: {path: text} to create first. approvals: answers for the write
    and command prompts, used in order (False once they run out). The trace
    keeps the answers actually used, so a replay can give the same ones.
    """
    for name, text in files.items():
        (workdir / name).parent.mkdir(parents=True, exist_ok=True)
        (workdir / name).write_text(text)

    remaining, used = list(approvals), []

    def approve(*question):  # a write (path, old, new) or a command (command)
        used.append(remaining.pop(0) if remaining else False)
        return used[-1]

    recorder = RecordingModel(model)
    messages = new_conversation()
    answers = [
        run_turn(recorder, messages, prompt, workdir, approve, approve_command=approve)
        for prompt in prompts
    ]
    return {
        "files_before": files,
        "prompts": prompts,
        "approvals": used,
        "answers": answers,
        "files_after": snapshot(workdir),
        "exchanges": recorder.exchanges,
    }


def first_difference(recorded, actual):
    for i, (want, got) in enumerate(zip(recorded, actual)):
        if want != got:
            return f"  message {i}\n  recorded: {want}\n  got:      {got}"
    return f"  recorded {len(recorded)} messages, got {len(actual)}"
