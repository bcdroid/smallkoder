"""Tests for smallkoder.tools: the two tools and their guardrails."""

import pytest

from smallkoder.tools import ToolError, read_file, resolve_path


@pytest.fixture
def root(tmp_path):
    """A workspace directory, resolved (tmp_path may sit behind a symlink)."""
    workspace = tmp_path / "work"
    workspace.mkdir()
    return workspace.resolve()


# --- resolve_path: confining paths to the working directory ---


def test_resolve_relative_path_inside_root(root):
    assert resolve_path(root, "src/app.py") == root / "src" / "app.py"


def test_resolve_allows_dotdot_that_stays_inside(root):
    assert resolve_path(root, "src/../app.py") == root / "app.py"


def test_resolve_refuses_parent_directory(root):
    with pytest.raises(ToolError, match="outside the working directory"):
        resolve_path(root, "../secret.txt")


def test_resolve_refuses_absolute_path_outside(root):
    with pytest.raises(ToolError, match="outside the working directory"):
        resolve_path(root, "/etc/passwd")


def test_resolve_refuses_symlink_pointing_outside(root, tmp_path):
    (tmp_path / "outside.txt").write_text("secret")
    (root / "link.txt").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(ToolError, match="outside the working directory"):
        resolve_path(root, "link.txt")


def test_resolve_refuses_env_files(root):
    with pytest.raises(ToolError, match="secret file"):
        resolve_path(root, ".env")
    with pytest.raises(ToolError, match="secret file"):
        resolve_path(root, "config/.env")


# --- read_file ---


def test_read_file_returns_contents(root):
    (root / "hello.py").write_text("print('hi')\n")
    assert read_file(root, "hello.py") == "print('hi')\n"


def test_read_file_missing(root):
    with pytest.raises(ToolError, match="file not found: nope.py"):
        read_file(root, "nope.py")


def test_read_file_directory(root):
    (root / "src").mkdir()
    with pytest.raises(ToolError, match="is a directory"):
        read_file(root, "src")


def test_read_file_not_text(root):
    (root / "image.bin").write_bytes(b"\xff\xfe\x00\x81")
    with pytest.raises(ToolError, match="not a UTF-8 text file"):
        read_file(root, "image.bin")
