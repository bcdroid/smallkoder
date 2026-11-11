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

CALC = '''def add(a, b):
    return a + b


def sub(a, b):
    return a - b
'''

# Big enough that the rename touches only a few lines, so editing beats rewriting.
SHAPES = '''"""Areas and perimeters of simple shapes."""

import math


def circle_area(radius):
    return math.pi * radius * radius


def circle_perimeter(radius):
    return 2 * math.pi * radius


def rectangle_area(width, height):
    return width * height


def rectangle_perimeter(width, height):
    return 2 * (width + height)


def triangle_area(base, height):
    return base * height / 2


def square_area(size):
    return size * size


def square_perimeter(size):
    return 4 * size


def describe(size):
    return f"A square of size {size} has area {square_area(size)}."


def largest(areas):
    """Return the name of the shape with the largest area."""
    return max(areas, key=areas.get)


def total_area(areas):
    return sum(areas.values())


def scale(area, factor):
    return area * factor * factor


def summary(areas):
    lines = [f"{name}: {area:.2f}" for name, area in sorted(areas.items())]
    lines.append(f"total: {total_area(areas):.2f}")
    return "\\n".join(lines)
'''

SCENARIOS = {
    "edit_function": {
        "description": "Change one of two similar functions with edit_file (edit approved).",
        "files": {"calc.py": CALC},
        "prompts": ["In calc.py, make sub return the absolute difference of a and b."],
        "approvals": [True],
    },
    "rename_everywhere": {
        "description": "Rename a name that appears many times, with edit_file (edits approved).",
        "files": {"shapes.py": SHAPES},
        "prompts": ["In shapes.py, rename the parameter size to side everywhere."],
        "approvals": [True, True, True, True, True, True],
    },
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
    # Commands run again for real on replay, so their output must not depend
    # on the machine or the time (no `ls -l`, no pytest timings).
    "run_program": {
        "description": "Run a program with run_command (approved) and report its output.",
        "files": {"hello.py": HELLO},
        "prompts": ["Use run_command to run `python3 hello.py` and tell me what it prints."],
        "approvals": [True],
    },
    "declined_command": {
        "description": "The user says no to a command; it must not run.",
        "files": {"notes.txt": "Remember the milk.\n"},
        "prompts": ["Use run_command to delete notes.txt with rm."],
        "approvals": [False],
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
