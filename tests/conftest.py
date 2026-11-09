"""Shared pytest setup.

Two guardrails live here:

1. No test may use the network unless it is marked ``live``. A test that
   accidentally calls the real API fails with a clear message instead of
   silently spending money (or passing only when the Wi-Fi works).
2. ``live`` tests are skipped unless SMALLKODER_LIVE=1 is set.
"""

import os
import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return

    def refuse(*args, **kwargs):
        raise RuntimeError(
            "This test tried to use the network. Use a fake model, "
            "or mark the test @pytest.mark.live."
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)  # DNS lookups too


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SMALLKODER_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="live API test; set SMALLKODER_LIVE=1")  # test-guard: live tests are opt-in by design
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
