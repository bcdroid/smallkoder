"""Tests for the test-suite guardrails in conftest.py."""

import socket

import pytest


def test_network_is_blocked_in_ordinary_tests():
    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("example.com", 80), timeout=1)
