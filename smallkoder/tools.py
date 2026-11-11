"""The tools the model can call, and the guardrails around them."""

import json
from pathlib import Path


def tool_schema(name: str, description: str, params: dict[str, str], flags: dict[str, str] | None = None) -> dict:
    """Describe a tool in the OpenAI chat completions format.

    params are required string arguments; flags are optional true/false
    arguments that default to false. Each maps a name to its description.
    """
    properties = {p: {"type": "string", "description": d} for p, d in params.items()}
    properties |= {f: {"type": "boolean", "description": d} for f, d in (flags or {}).items()}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
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
    tool_schema(
        "edit_file",
        "Change part of an existing file by replacing old_text with new_text. old_text must "
        "match the file exactly, including indentation and line breaks, and must appear "
        "exactly once: include enough surrounding lines to make it unique. Set replace_all "
        "to true to replace every occurrence instead. The user must approve each edit.",
        {
            "path": "File path, relative to the working directory.",
            "old_text": "The exact text to find in the file.",
            "new_text": "The text to put in its place (may be empty, to delete).",
        },
        {"replace_all": "Optional, default false: replace every occurrence of old_text, not just one."},
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


def match_lines(text: str, part: str) -> list[int]:
    """The line number where each occurrence of part starts (not overlapping,
    the same occurrences str.count and str.replace see)."""
    lines, start = [], text.find(part)
    while start != -1:
        lines.append(text.count("\n", 0, start) + 1)
        start = text.find(part, start + len(part))
    return lines


def without_line_end_spaces(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.split("\n"))


def edit_file(root: Path, path: str, old_text: str, new_text: str, replace_all: bool, approve) -> str:
    """Replace old_text with new_text in an existing file, if the user approves.

    old_text must match exactly, and only once unless replace_all is true:
    an edit that might land in the wrong place is refused, and the error
    says what to fix. approve() sees the whole old and new file, as for
    write_file, so the user is shown a diff.
    """
    old_file = read_file(root, path)  # path checks, missing file, directory, not UTF-8
    if old_text == "":
        raise ToolError("old_text is empty. To create a file, use write_file")
    if old_text == new_text:
        raise ToolError("old_text and new_text are the same, so there is nothing to change")

    lines = match_lines(old_file, old_text)
    if not lines:
        hint = ""
        if without_line_end_spaces(old_text) in without_line_end_spaces(old_file):
            hint = " (It would match if spaces at the ends of lines were ignored: check the whitespace.)"
        raise ToolError(
            f"old_text not found in {path}. It must match the file exactly, including "
            f"indentation and line breaks. Read the file again and copy the text.{hint}"
        )
    if len(lines) > 1 and not replace_all:
        raise ToolError(
            f"old_text appears {len(lines)} times in {path} (lines {', '.join(map(str, lines))}). "
            "Include more surrounding lines so it matches only once, or set replace_all to true "
            "to change every one."
        )

    new_file = old_file.replace(old_text, new_text, -1 if replace_all else 1)
    if not approve(path, old_file, new_file):
        raise ToolError("the user declined this write")
    resolve_path(root, path).write_text(new_file, encoding="utf-8")
    count = len(lines) if replace_all else 1
    return f"Edited {path}: replaced {count} occurrence{'s' if count > 1 else ''}"


JSON_TYPES = {"string": str, "boolean": bool}


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

    properties, required = schemas[name]["properties"], schemas[name]["required"]
    unexpected = [key for key in args if key not in properties]
    if unexpected:
        raise ToolError(f"{name} got unexpected arguments {', '.join(map(repr, unexpected))}")
    flags = [key for key in properties if key not in required]
    args |= {flag: args.get(flag, False) for flag in flags}  # optional flags default to false
    if not all(isinstance(args.get(key), JSON_TYPES[spec["type"]]) for key, spec in properties.items()):
        needs = f"{name} needs string arguments {', '.join(map(repr, required))}"
        raise ToolError(needs + (f" (and optionally true/false {', '.join(map(repr, flags))})" if flags else ""))
    return args


def run_tool(name: str, arguments: str, root: Path, approve) -> str:
    """Run one tool call. Always returns text for the model, even on errors."""
    try:
        args = parse_arguments(name, arguments)
        if name == "read_file":
            return read_file(root, args["path"])
        if name == "edit_file":
            return edit_file(root, args["path"], args["old_text"], args["new_text"], args["replace_all"], approve)
        return write_file(root, args["path"], args["content"], approve)
    except ToolError as e:
        return f"Error: {e}"
