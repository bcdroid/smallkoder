"""Fake models for tests. No network, no key, same answers every time.

A model is anything with complete(messages, tools) -> assistant message.
"""

import copy
import json


def answer(text):
    """An assistant reply with no tool calls: the turn ends."""
    return {"role": "assistant", "content": text}


def tool_calls(*calls):
    """An assistant reply asking for tools. Each call is (name, arguments).

    arguments may be a dict (encoded to JSON for you) or a raw string, so
    tests can send malformed JSON on purpose.
    """
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args if isinstance(args, str) else json.dumps(args),
                },
            }
            for i, (name, args) in enumerate(calls, start=1)
        ],
    }


class ScriptedModel:
    """Returns the given replies in order, and remembers every request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []  # (messages, tools) for each call, copied

    def complete(self, messages, tools):
        self.requests.append((copy.deepcopy(messages), tools))
        if not self.replies:
            raise AssertionError("ScriptedModel ran out of replies")
        return self.replies.pop(0)


class EndlessToolModel:
    """Fault injection: a model that never stops asking for tools."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        return tool_calls(("read_file", {"path": "loop.txt"}))
