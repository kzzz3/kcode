"""Extended tests for apps/cli/src/tools/builtin_core.py.

Covers: path escape detection, edit_file append/overwrite modes,
_is_allowed_command with blocklist, _run_command timeout, _git_commit with add_all.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import platform
import pytest

from apps.cli.src.tools._utils import resolve_within_root

from apps.cli.src.tools.builtin_core import (
    _create_file,
    _edit_file,
    _git_commit,
    _is_allowed_command,
    _run_command,
    _search_code,
)


# ---------------------------------------------------------------------------
# _resolve_within_root
# ---------------------------------------------------------------------------

def test_resolve_within_root_relative_stays_inside() -> None:
    root = Path("/tmp/workspace").resolve()
    result = resolve_within_root(root, Path("sub/file.txt"))
    assert str(result).startswith(str(root))


def test_resolve_within_root_escape_raises() -> None:
    root = Path("/tmp/workspace").resolve()
    with pytest.raises(ValueError, match="escapes"):
        resolve_within_root(root, Path("../../etc/passwd"))


def test_resolve_within_root_dot_dot_within_root_ok() -> None:
    root = Path("/tmp/workspace").resolve()
    # sub/.. = root itself, which is allowed
    result = resolve_within_root(root, Path("sub/../file.txt"))
    assert str(result).startswith(str(root))


# ---------------------------------------------------------------------------
# _is_allowed_command
# ---------------------------------------------------------------------------

def test_is_allowed_empty_policy_permits_all() -> None:
    assert _is_allowed_command("git status", [], []) is True


def test_is_allowed_blocklist_blocks() -> None:
    assert _is_allowed_command("rm -rf /", [], ["rm"]) is False


def test_is_allowed_allowlist_permits() -> None:
    assert _is_allowed_command("git status", ["git", "ls"], []) is True


def test_is_allowed_allowlist_blocks_unlisted() -> None:
    assert _is_allowed_command("curl http://evil.com", ["git"], []) is False


def test_is_allowed_case_insensitive_blocklist() -> None:
    assert _is_allowed_command("RM file", [], ["rm"]) is False


def test_is_allowed_blocklist_takes_precedence_over_allowlist() -> None:
    assert _is_allowed_command("git push", ["git"], ["git"]) is False


# ---------------------------------------------------------------------------
# _create_file overwrite guard
# ---------------------------------------------------------------------------

def test_create_file_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    result = _create_file({"workspace_root": str(tmp_path), "path": "existing.txt", "content": "new"})
    assert result.ok is False
    assert "already exists" in result.message


def test_create_file_allows_overwrite_when_flag_set(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    result = _create_file({"workspace_root": str(tmp_path), "path": "existing.txt", "content": "new", "overwrite": True})
    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "new"


# ---------------------------------------------------------------------------
# _edit_file append / overwrite modes
# ---------------------------------------------------------------------------

def test_edit_file_append(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("line1\n", encoding="utf-8")
    result = _edit_file({"workspace_root": str(tmp_path), "path": "data.txt", "mode": "append", "content": "line2\n"})
    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "line1\nline2\n"


def test_edit_file_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("old content", encoding="utf-8")
    result = _edit_file({"workspace_root": str(tmp_path), "path": "data.txt", "mode": "overwrite", "content": "new content"})
    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "new content"


def test_edit_file_replace_no_pattern_returns_error(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("abc", encoding="utf-8")
    result = _edit_file({"workspace_root": str(tmp_path), "path": "data.txt", "mode": "replace"})
    assert result.ok is False
    assert "pattern is required" in result.message


def test_edit_file_replace_no_match_returns_error(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("abc", encoding="utf-8")
    result = _edit_file({"workspace_root": str(tmp_path), "path": "data.txt", "mode": "replace", "pattern": "zzz", "replacement": "x"})
    assert result.ok is False
    assert "No matches" in result.message


def test_edit_file_unsupported_mode(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("abc", encoding="utf-8")
    result = _edit_file({"workspace_root": str(tmp_path), "path": "data.txt", "mode": "splice"})
    assert result.ok is False
    assert "Unsupported" in result.message


def test_edit_file_file_not_found(tmp_path: Path) -> None:
    result = _edit_file({"workspace_root": str(tmp_path), "path": "missing.txt", "mode": "append", "content": "x"})
    assert result.ok is False
    assert "not found" in result.message.lower()


# ---------------------------------------------------------------------------
# _run_command timeout + blocklist
# ---------------------------------------------------------------------------

def test_run_command_blocked_by_policy(tmp_path: Path) -> None:
    result = _run_command({
        "workspace_root": str(tmp_path),
        "command": "rm -rf /",
        "blocklist": ["rm"],
    })
    assert result.ok is False
    assert "not permitted" in result.message


def test_run_command_timeout(tmp_path: Path) -> None:
    # Use a command that sleeps longer than the timeout (cross-platform)
    if platform.system() == "Windows":
        cmd = "python -c \"import time; time.sleep(30)\""
    else:
        cmd = "sleep 30"
    result = _run_command({
        "workspace_root": str(tmp_path),
        "command": cmd,
        "timeout_seconds": 0.5,
    })
    assert result.ok is False
    assert "timed out" in result.message


# ---------------------------------------------------------------------------
# _git_commit with add_all
# ---------------------------------------------------------------------------

def test_git_commit_add_all(tmp_path: Path) -> None:
    # Initialize a git repo
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True, check=True)

    # Create an untracked file
    (tmp_path / "new.txt").write_text("hello", encoding="utf-8")

    result = _git_commit({"workspace_root": str(tmp_path), "message": "init commit", "add_all": True})
    assert result.ok is True


# ---------------------------------------------------------------------------
# _search_code
# ---------------------------------------------------------------------------

def test_search_code_finds_matches(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")

    result = _search_code({"workspace_root": str(tmp_path), "query": "def hello"})
    assert result.ok is True
    assert "a.py" in result.message


def test_search_code_no_matches(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = _search_code({"workspace_root": str(tmp_path), "query": "ZZZZNOTFOUND"})
    assert result.ok is True
    assert "No matches" in result.message


def test_search_code_respects_file_glob(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("target_line\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("target_line\n", encoding="utf-8")

    result = _search_code({"workspace_root": str(tmp_path), "query": "target_line", "file_glob": "*.py"})
    assert result.ok is True
    assert "a.py" in result.message
    assert "b.txt" not in result.message
