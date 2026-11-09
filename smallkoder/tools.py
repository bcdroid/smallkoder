"""The tools the model can call, and the guardrails around them."""

import json
from pathlib import Path


def tool_schema(name: str, description: str, params: dict[str, str]) -> dict:
    """Describe a tool whose arguments are all required strings, in the
    OpenAI chat completions format."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {p: {"type": "string", "description": d} for p, d in params.items()},
                "required": list(params),
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    tool_schema(
        "read_file",
        "Read a text file in the working directory and return its contents.",
        {"path": "File path, relative to the working directory."},
    ),
    tool_schema(
        "write_file",
        "Replace the entire contents of a file, creating it if needed. Always send the "
        "complete new file, not just the changed part. The user must approve each write.",
        {
            "path": "File path, relative to the working directory.",
            "content": "The complete new contents of the file.",
        },
    ),
]


class ToolError(Exception):
    """A problem the model caused and can fix, e.g. a missing file.

    These are reported back to the model as tool results, never as crashes.
    """


def resolve_path(root: Path, path: str) -> Path:
    """Turn the model's path into an absolute path inside root, or refuse.

    resolve() removes '..' and follows symlinks *before* we check, so
    '../x', '/etc/passwd' and a symlink pointing outside are all caught.
    """
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ToolError(f"path '{path}' is outside the working directory")
    if target.name == ".env":
        raise ToolError(f"refusing to touch secret file '{path}'")
    return target


def read_file(root: Path, path: str) -> str:
    target = resolve_path(root, path)
    if target.is_dir():
        raise ToolError(f"'{path}' is a directory, not a file")
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ToolError(f"file not found: {path}")
    except UnicodeDecodeError:
        raise ToolError(f"'{path}' is not a UTF-8 text file")


def write_file(root: Path, path: str, content: str, approve) -> str:
    """Replace the whole file with content, if the user approves.

    approve(path, old_text, new_text) -> bool asks the user. old_text is
    None when the file does not exist yet.
    """
    target = resolve_path(root, path)  # refuse bad paths before asking
    if target.is_dir():
        raise ToolError(f"'{path}' is a directory, not a file")
    old_text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else None
    if not approve(path, old_text, content):
        raise ToolError("the user declined this write")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.splitlines())} lines to {path}"


def parse_arguments(name: str, arguments: str) -> dict:
    """Check the model's JSON argument string against the tool's schema."""
    schemas = {tool["function"]["name"]: tool["function"]["parameters"] for tool in TOOLS}
    if name not in schemas:
        raise ToolError(f"unknown tool '{name}'. Available tools: {', '.join(schemas)}")
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError as e:
        raise ToolError(f"arguments must be a JSON object: {e}")
    if not isinstance(args, dict):
        raise ToolError(f"arguments must be a JSON object, not {type(args).__name__}")

    expected = schemas[name]["required"]
    unexpected = [key for key in args if key not in expected]
    if unexpected:
        raise ToolError(f"{name} got unexpected arguments {', '.join(map(repr, unexpected))}")
    if not all(isinstance(args.get(key), str) for key in expected):
        raise ToolError(f"{name} needs string arguments {', '.join(map(repr, expected))}")
    return args


def run_tool(name: str, arguments: str, root: Path, approve) -> str:
    """Run one tool call. Always returns text for the model, even on errors."""
    try:
        args = parse_arguments(name, arguments)
        if name == "read_file":
            return read_file(root, args["path"])
        return write_file(root, args["path"], args["content"], approve)
    except ToolError as e:
        return f"Error: {e}"
