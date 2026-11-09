"""The tools the model can call, and the guardrails around them."""

from pathlib import Path


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
