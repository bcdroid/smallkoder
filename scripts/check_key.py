"""Check that the OpenCode Go API key works, with one tiny request.

Usage (from the repository root, with OPENCODE_GO in the environment or .env):

    python scripts/check_key.py

Sends one short prompt to the default model through the same code smallkoder
uses (OpenCodeModel), so it checks the endpoint, headers and key together.
The key is never printed: errors come from ModelError, which strips it.
Costs a tiny fraction of a cent.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `import smallkoder` works from scripts/

from smallkoder.model import DEFAULT_MODEL, ENDPOINT, ModelError, OpenCodeModel, load_api_key  # noqa: E402


def main() -> int:
    print(f"endpoint: {ENDPOINT}")
    print(f"model:    {DEFAULT_MODEL}")
    try:
        key = load_api_key(os.environ, ROOT / ".env")
        # Reasoning models think before answering, so allow more than a few tokens.
        model = OpenCodeModel(key, max_tokens=64)
        reply = model.complete([{"role": "user", "content": "Reply with the single word: ok"}], [])
    except ModelError as e:
        print(f"FAILED: {e}")
        return 1
    print(f"OK: the key works (reply: {reply.get('content')!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
