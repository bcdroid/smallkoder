"""The interactive command line: read a line, run a turn, print the answer."""

import argparse
import difflib
import os
import sys
from pathlib import Path

from smallkoder.agent import new_conversation, run_turn
from smallkoder.model import DEFAULT_MODEL, ModelError, OpenCodeModel, load_api_key


def make_diff(path: str, old_text: str | None, new_text: str) -> str:
    """A unified diff, like `git diff`, of the proposed write."""
    diff = difflib.unified_diff(
        (old_text or "").splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="/dev/null" if old_text is None else path,
        tofile=path,
    )
    return "".join(line if line.endswith("\n") else line + "\n" for line in diff)


def shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def repl(model, root: Path, input=input, output=print):
    """Chat until the user types exit/quit or presses Ctrl-D / Ctrl-C."""

    def approve(path, old_text, new_text):
        output(f"  The model wants to {'create' if old_text is None else 'change'} {path}:")
        output(make_diff(path, old_text, new_text).rstrip("\n"))
        try:
            reply = input("  Allow this write? [y/N] ")
        except EOFError:
            return False
        return reply.strip().lower() in ("y", "yes")

    def approve_command(command):
        output(f"  The model wants to run: {command}")  # in full: never approve a shortened command
        try:
            reply = input("  Run this command? [y/N] ")
        except EOFError:
            return False
        return reply.strip().lower() in ("y", "yes")

    def show_tool(name, arguments):
        output(f"  [{name}] {shorten(arguments)}")

    output(f"smallkoder ({getattr(model, 'model', 'model')}) in {root}. Type 'exit' or Ctrl-D to quit.")
    messages = new_conversation()
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            output("")
            return
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            return

        checkpoint = len(messages)
        try:
            output(run_turn(model, messages, line, root, approve, on_tool=show_tool, approve_command=approve_command))
        except ModelError as e:
            output(f"API error: {e}")
            del messages[checkpoint:]  # forget the failed turn; the user can retry
        except KeyboardInterrupt:
            output("\n(interrupted)")
            return


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="smallkoder", description="A small CLI coding assistant.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenCode Go model id (default {DEFAULT_MODEL})")
    args = parser.parse_args(argv)
    try:
        key = load_api_key(os.environ, Path(".env"))
    except ModelError as e:
        print(f"smallkoder: {e}", file=sys.stderr)
        return 1
    repl(OpenCodeModel(key, model=args.model), Path.cwd().resolve())
    return 0
