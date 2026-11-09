"""Re-record the traces in tests/traces/ against the real OpenCode Go API.

Usage (from the repository root, with OPENCODE_GO in the environment or .env):

    uv run scripts/record_traces.py                 # record every scenario
    uv run scripts/record_traces.py add_docstring   # just one

Each scenario runs in a fresh temporary directory. The trace files contain
messages and replies only: never the key or any HTTP headers.
Re-record after changing the system prompt, tool schemas or anything else
that changes what the model is sent; the replay tests will tell you when.
Costs a fraction of a cent.
"""

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `import smallkoder` works from scripts/

from smallkoder.model import DEFAULT_MODEL, OpenCodeModel, load_api_key  # noqa: E402
from smallkoder.traces import record_session  # noqa: E402

HELLO = '''def greet(name):
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("world"))
'''

SCENARIOS = {
    "add_docstring": {
        "description": "Read a file, then rewrite it with a docstring (write approved).",
        "files": {"hello.py": HELLO},
        "prompts": ["Read hello.py and add a docstring to the greet function."],
        "approvals": [True],
    },
    "explain_file": {
        "description": "Read-only question about a file.",
        "files": {"notes.txt": "Meeting moved to Thursday at 3pm in room 204.\nBring the slides.\n"},
        "prompts": ["What does notes.txt say? Answer in one sentence."],
        "approvals": [],
    },
    "declined_write": {
        "description": "The user says no to a write; the file must not change.",
        "files": {"config.py": "DEBUG = False\n"},
        "prompts": ["Change DEBUG to True in config.py."],
        "approvals": [False],
    },
    "missing_file": {
        "description": "The model reads a file that does not exist and gets an error result.",
        "files": {},
        "prompts": ["Read missing.py and tell me what it does."],
        "approvals": [],
    },
    "outside_workspace": {
        "description": "The model is asked to read outside the working directory and is refused.",
        "files": {},
        "prompts": ["Use read_file on ../secret.txt and tell me what it says."],
        "approvals": [],
    },
    "two_turns": {
        "description": "Two user turns in one conversation: create a file, then read it back.",
        "files": {},
        "prompts": [
            "Create a file named greeting.txt containing exactly one line: hi there",
            "Now read greeting.txt and tell me what it says.",
        ],
        "approvals": [True],
    },
}


def main(names):
    key = load_api_key(os.environ, ROOT / ".env")
    out_dir = ROOT / "tests" / "traces"
    for name in names or SCENARIOS:
        scenario = SCENARIOS[name]
        with tempfile.TemporaryDirectory() as tmp:
            trace = record_session(
                OpenCodeModel(key),
                scenario["files"],
                scenario["prompts"],
                scenario["approvals"],
                Path(tmp).resolve(),
            )
        data = {
            "description": scenario["description"],
            "model": DEFAULT_MODEL,
            "recorded": datetime.date.today().isoformat(),
            **trace,
        }
        (out_dir / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"{name}: {len(trace['exchanges'])} model calls; answers: {trace['answers']}")


if __name__ == "__main__":
    main(sys.argv[1:])
