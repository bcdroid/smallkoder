"""Tests for smallkoder.model: building requests and reading responses.

No network: OpenCodeModel takes a `post` function, and here we pass fakes.
"""

import io
import json
import urllib.error

import pytest

from smallkoder import model as model_module
from smallkoder.model import ENDPOINT, ModelError, OpenCodeModel, http_post_json, load_api_key

KEY = "oc_sk_test_not_a_real_key"

# A real response from OpenCode Go (2026-11-09), with ids shortened.
TOOL_CALL_RESPONSE = {
    "id": "gen-1",
    "object": "chat.completion",
    "model": "mimo-v2.6-flash",
    "choices": [{
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "refusal": None,
            "reasoning": "The user asks what is in hello.py. Use the read_file tool.",
            "reasoning_details": [{"type": "reasoning.text", "text": "...", "index": 0}],
            "tool_calls": [{
                "index": 0,
                "id": "call_2b4e",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "hello.py"}'},
            }],
        },
    }],
    "usage": {"prompt_tokens": 94, "completion_tokens": 35},
}


class FakePost:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.response


def test_endpoint_is_opencode_go_chat_completions():
    assert ENDPOINT == "https://opencode.ai/inference/go/openai/v1/chat/completions"


def test_request_shape():
    post = FakePost(TOOL_CALL_RESPONSE)
    model = OpenCodeModel(KEY, post=post)
    messages = [{"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "t"}}]

    model.complete(messages, tools)

    url, headers, body = post.calls[0]
    assert url == ENDPOINT
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"].startswith("smallkoder/")
    assert headers["x-opencode-session"].startswith("ses_")
    assert body == {"model": "mimo-v2.6-flash", "messages": messages, "tools": tools, "max_tokens": 4096}


def test_one_session_id_per_model_instance():
    post = FakePost(TOOL_CALL_RESPONSE)
    model = OpenCodeModel(KEY, post=post)
    model.complete([], [])
    model.complete([], [])
    other = OpenCodeModel(KEY, post=post)
    other.complete([], [])
    sessions = [headers["x-opencode-session"] for _, headers, _ in post.calls]
    assert sessions[0] == sessions[1] != sessions[2]


def test_model_name_can_be_changed():
    post = FakePost(TOOL_CALL_RESPONSE)
    OpenCodeModel(KEY, model="glm-5.3-flash", post=post).complete([], [])
    assert post.calls[0][2]["model"] == "glm-5.3-flash"


def test_reply_keeps_only_standard_fields():
    reply = OpenCodeModel(KEY, post=FakePost(TOOL_CALL_RESPONSE)).complete([], [])
    assert reply == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_2b4e",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path": "hello.py"}'},
        }],
    }


def test_plain_answer_has_no_tool_calls_key():
    response = {"choices": [{"message": {"role": "assistant", "content": "Hi!"}}]}
    reply = OpenCodeModel(KEY, post=FakePost(response)).complete([], [])
    assert reply == {"role": "assistant", "content": "Hi!"}


@pytest.mark.parametrize("response", [{}, {"choices": []}, {"choices": [{}]}, {"error": "boom"}])
def test_malformed_response_raises_model_error(response):
    with pytest.raises(ModelError, match="unexpected response"):
        OpenCodeModel(KEY, post=FakePost(response)).complete([], [])


@pytest.mark.parametrize("bad_call", [{}, {"id": "c1"}, {"id": "c1", "function": {"name": "x"}}])
def test_malformed_tool_call_in_response_raises_model_error(bad_call):
    response = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [bad_call]}}]}
    with pytest.raises(ModelError, match="unexpected response"):
        OpenCodeModel(KEY, post=FakePost(response)).complete([], [])


def test_repr_does_not_show_the_key():
    assert KEY not in repr(OpenCodeModel(KEY, post=FakePost({})))


# --- http_post_json: the only code that touches the network ---


def fake_urlopen(error):
    def urlopen(request, timeout):
        raise error

    return urlopen


def test_http_error_becomes_model_error_without_the_key(monkeypatch):
    body = io.BytesIO(json.dumps({"error": {"message": "This API key has expired."}}).encode())
    error = urllib.error.HTTPError(ENDPOINT, 401, "Unauthorized", {}, body)
    monkeypatch.setattr(model_module.urllib.request, "urlopen", fake_urlopen(error))

    with pytest.raises(ModelError) as caught:
        http_post_json(ENDPOINT, {"Authorization": f"Bearer {KEY}"}, {})
    assert "HTTP 401" in str(caught.value)
    assert "expired" in str(caught.value)
    assert KEY not in str(caught.value)


def test_network_error_becomes_model_error(monkeypatch):
    monkeypatch.setattr(model_module.urllib.request, "urlopen", fake_urlopen(urllib.error.URLError("no route")))
    with pytest.raises(ModelError, match="could not reach"):
        http_post_json(ENDPOINT, {}, {})


def test_timeout_becomes_model_error(monkeypatch):
    monkeypatch.setattr(model_module.urllib.request, "urlopen", fake_urlopen(TimeoutError()))
    with pytest.raises(ModelError, match="could not reach"):
        http_post_json(ENDPOINT, {}, {})


def test_non_json_response_becomes_model_error(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(model_module.urllib.request, "urlopen", lambda request, timeout: Response(b"<html>oops"))
    with pytest.raises(ModelError, match="not JSON"):
        http_post_json(ENDPOINT, {}, {})


# --- load_api_key ---


def test_key_from_environment_wins(tmp_path):
    (tmp_path / ".env").write_text("OPENCODE_GO=from-file\n")
    assert load_api_key({"OPENCODE_GO": "from-env"}, tmp_path / ".env") == "from-env"


def test_key_from_env_file(tmp_path):
    (tmp_path / ".env").write_text('# comment\nOTHER=x\nOPENCODE_GO="from-file"\n')
    assert load_api_key({}, tmp_path / ".env") == "from-file"


def test_missing_key(tmp_path):
    with pytest.raises(ModelError, match="OPENCODE_GO"):
        load_api_key({}, tmp_path / ".env")
