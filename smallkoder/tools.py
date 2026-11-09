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
