"""The agent loop: ask the model, run the tools it asks for, repeat."""

from pathlib import Path

from smallkoder.tools import TOOLS, run_tool

# Kept short (pi gets by with a few sentences). No absolute paths in here:
# recorded traces must replay the same on any machine.
SYSTEM_PROMPT = (
    "You are smallkoder, a small coding assistant working in the user's project directory. "
    "You have three tools: read_file returns a file's contents, edit_file replaces exact text "
    "in a file, and write_file replaces a whole file or creates a new one. Use paths relative "
    "to the project directory. Read a file before changing it. To change part of a file, use "
    "edit_file; use write_file for new files. The user approves every change; if they "
    "decline, do not try again unless they ask. Keep your answers short."
)


def new_conversation() -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def run_turn(model, messages, user_text, root: Path, approve, max_steps=20, on_tool=None) -> str:
    """Handle one user message and return the model's final answer.

    Appends everything (user message, model replies, tool results) to
    messages, which holds the whole conversation between turns.
    on_tool(name, arguments), if given, is called before each tool runs.
    """
    messages.append({"role": "user", "content": user_text})
    for _ in range(max_steps):
        reply = model.complete(messages, TOOLS)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return reply.get("content") or ""

        for call in reply["tool_calls"]:
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]
            if on_tool:
                on_tool(name, arguments)
            result = run_tool(name, arguments, root, approve)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    return f"(stopped: {max_steps} steps without a final answer)"
