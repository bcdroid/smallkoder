"""Talking to the language model.

Everything else in smallkoder sees a model as one method,
complete(messages, tools) -> assistant message, so tests can swap in fakes.
This is the only module that uses the network.
"""

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Protocol

ENDPOINT = "https://opencode.ai/inference/go/openai/v1/chat/completions"
DEFAULT_MODEL = "mimo-v2.6-flash"
KEY_NAME = "OPENCODE_GO"


class ModelError(Exception):
    """The API call failed (network, HTTP error, bad response). Never contains the key."""


class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return the assistant's reply: {"role", "content", and maybe "tool_calls"}."""


def http_post_json(url: str, headers: dict, body: dict, timeout: float = 120) -> dict:
    """POST body as JSON and return the JSON response, or raise ModelError."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            detail = detail[:300]
        secret = headers.get("Authorization", "").removeprefix("Bearer ")
        if secret:
            detail = detail.replace(secret, "<key>")
        raise ModelError(f"HTTP {e.code}: {detail}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise ModelError(f"could not reach the API: {e}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ModelError(f"the API's response was not JSON: {text[:200]}")


class OpenCodeModel:
    """The real model: OpenCode Go's OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, post=http_post_json, max_tokens: int = 4096):
        self._api_key = api_key
        self.model = model
        self.post = post
        # Reasoning models spend tokens thinking before they answer; leave room.
        self.max_tokens = max_tokens
        # OpenCode Go requires a session id; one per conversation.
        self.session_id = "ses_" + uuid.uuid4().hex

    def __repr__(self):
        return f"OpenCodeModel(model={self.model!r})"  # never show the key

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "smallkoder/0.1",
            "x-opencode-session": self.session_id,
        }
        body = {"model": self.model, "messages": messages, "tools": tools, "max_tokens": self.max_tokens}
        response = self.post(ENDPOINT, headers, body)
        try:
            return clean_reply(response["choices"][0]["message"])
        except (KeyError, IndexError, TypeError):
            raise ModelError(f"unexpected response from the API: {str(response)[:200]}")


def clean_reply(message: dict) -> dict:
    """Keep only the standard fields, dropping extras like 'reasoning'."""
    reply = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        reply["tool_calls"] = [
            {
                "id": call["id"],
                "type": "function",
                "function": {"name": call["function"]["name"], "arguments": call["function"]["arguments"]},
            }
            for call in message["tool_calls"]
        ]
    return reply


def load_api_key(environ, env_file: Path) -> str:
    """The key from the environment, or else from a .env file. Never print it."""
    if environ.get(KEY_NAME):
        return environ[KEY_NAME]
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == KEY_NAME:
                return value.strip().strip("\"'")
    raise ModelError(f"no API key: set {KEY_NAME} in the environment or in a .env file")
