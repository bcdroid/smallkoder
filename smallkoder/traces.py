"""Record real model calls to a JSON file, and replay them in tests.

A trace is a list of exchanges: {"request": {"messages", "tools"}, "response"}.
Only messages and tools are recorded. The API key and headers never reach
complete(), so they cannot end up in a trace.
"""

import copy
import json
from pathlib import Path


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
        recorded = self.exchanges[self.position]["request"]
        self.position += 1
        if tools != recorded["tools"]:
            raise TraceMismatch(f"request {self.position} sent different tools than recorded")
        if messages != recorded["messages"]:
            raise TraceMismatch(f"request {self.position} differs from the trace:\n" + first_difference(recorded["messages"], messages))
        return copy.deepcopy(self.exchanges[self.position - 1]["response"])


def first_difference(recorded, actual):
    for i, (want, got) in enumerate(zip(recorded, actual)):
        if want != got:
            return f"  message {i}\n  recorded: {want}\n  got:      {got}"
    return f"  recorded {len(recorded)} messages, got {len(actual)}"
