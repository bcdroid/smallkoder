"""Real-API tests. Skipped unless you opt in, because they need a key,
cost (a tiny amount of) money, and the model's answers vary:

    SMALLKODER_LIVE=1 python -m pytest -m live
"""

import os
from pathlib import Path

import pytest

from smallkoder.agent import new_conversation, run_turn
from smallkoder.model import OpenCodeModel, load_api_key

pytestmark = pytest.mark.live

REPO = Path(__file__).parent.parent


def test_real_model_reads_a_file(tmp_path):
    root = tmp_path.resolve()
    (root / "fact.txt").write_text("The secret number is 4817.\n")
    model = OpenCodeModel(load_api_key(os.environ, REPO / ".env"))
    messages = new_conversation()

    answer = run_turn(model, messages, "What is the secret number in fact.txt?", root, lambda *a: False)

    assert any(m["role"] == "tool" and "4817" in m["content"] for m in messages)
    assert "4817" in answer
