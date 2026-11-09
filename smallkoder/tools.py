"""The tools the model can call, and the guardrails around them."""

import json
import os
import signal
import subprocess
from pathlib import Path

COMMAND_TIMEOUT = 30  # seconds
OUTPUT_LIMIT = 10_000  # characters of command output sent back to the model


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
    tool_schema(
        "run_command",
        "Run a shell command with bash in the working directory and return its exit code "
        f"and output (stdout and stderr together, at most the last {OUTPUT_LIMIT} characters). "
        f"Commands time out after {COMMAND_TIMEOUT} seconds and cannot read input. "
        "The user must approve each command.",
        {"command": "The shell command to run."},
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


def keep_end(text: str, limit: int = OUTPUT_LIMIT) -> str:
    """At most limit characters: the end, where errors and summaries usually are."""
    if len(text) <= limit:
        return text
    return f"[... {len(text) - limit} characters cut ...]\n" + text[-limit:]


def run_command(root: Path, command: str, approve_command, timeout: float = COMMAND_TIMEOUT) -> str:
    """Run command with bash in root, if the user approves.

    Unlike the file tools, there is no path check here: a command can touch
    anything the user can. The approval prompt is the only guardrail.
    """
    if not command.strip():
        raise ToolError("command is empty")
    if not approve_command(command):
        raise ToolError("the user declined this command")

    env = {name: value for name, value in os.environ.items() if name != "OPENCODE_GO"}
    process = subprocess.Popen(
        ["bash", "-c", command],
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,  # a command waiting for input gets EOF, not a hang
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # one stream, in the order it was written
        start_new_session=True,  # its own process group, so we can kill all of it
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the whole group: a background child (`server &`) would
        # otherwise keep the pipe open and we would wait for it forever.
        kill_group(process)
        output, _ = process.communicate()  # what it printed before the timeout
        text = keep_end(output.decode("utf-8", errors="replace"))
        raise ToolError(f"command timed out after {timeout} s. Output so far:\n{text}")
    except BaseException:
        # Ctrl-C goes to smallkoder, not to the command (it has its own
        # session), so stop the command before letting the interrupt through.
        kill_group(process)
        raise
    return f"Exit code: {process.returncode}\n{keep_end(output.decode('utf-8', errors='replace'))}"


def kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # already gone
    process.wait()


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


def never(command: str) -> bool:
    return False


def run_tool(name: str, arguments: str, root: Path, approve, approve_command=never) -> str:
    """Run one tool call. Always returns text for the model, even on errors.

    approve(path, old_text, new_text) -> bool asks about writes, and
    approve_command(command) -> bool about commands (by default: no).
    """
    try:
        args = parse_arguments(name, arguments)
        if name == "read_file":
            return read_file(root, args["path"])
        if name == "run_command":
            return run_command(root, args["command"], approve_command)
        return write_file(root, args["path"], args["content"], approve)
    except ToolError as e:
        return f"Error: {e}"
