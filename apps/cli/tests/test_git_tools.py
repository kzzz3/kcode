"""Tests for _git_log and _git_checkout in builtin_core."""
from __future__ import annotations

import subprocess
from pathlib import Path


from apps.cli.src.tools.builtin_core import _git_checkout, _git_log


def _init_git_repo(path: Path) -> None:
  """Helper: initialize a git repo with one commit."""
  subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
  subprocess.run(["git", "config", "user.email", "test@test.com"],
                 cwd=str(path), capture_output=True, check=True)
  subprocess.run(["git", "config", "user.name", "Test User"],
                 cwd=str(path), capture_output=True, check=True)
  (path / "init.txt").write_text("initial", encoding="utf-8")
  subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, check=True)
  subprocess.run(["git", "commit", "-m", "init commit"],
                 cwd=str(path), capture_output=True, check=True)


class TestGitLog:
  """_git_log returns formatted commit history."""

  def test_log_returns_commits(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = _git_log({"workspace_root": str(tmp_path)})
    assert out.ok is True
    assert "init commit" in out.message

  def test_log_oneline_format(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = _git_log({"workspace_root": str(tmp_path), "oneline": True})
    assert out.ok is True
    assert "init commit" in out.message

  def test_log_with_count(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    # Add a second commit
    (tmp_path / "second.txt").write_text("second", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "second commit"],
                   cwd=str(tmp_path), capture_output=True, check=True)

    out = _git_log({"workspace_root": str(tmp_path), "count": 1})
    assert out.ok is True
    assert "second commit" in out.message
    assert "init commit" not in out.message

  def test_log_not_a_repo(self, tmp_path: Path) -> None:
    out = _git_log({"workspace_root": str(tmp_path)})
    assert out.ok is False


class TestGitCheckout:
  """_git_checkout switches and creates branches."""

  def test_checkout_existing_branch(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    # Create a branch
    subprocess.run(["git", "branch", "feature"], cwd=str(tmp_path),
                   capture_output=True, check=True)
    out = _git_checkout({"workspace_root": str(tmp_path), "branch": "feature"})
    assert out.ok is True

  def test_checkout_create_new_branch(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = _git_checkout({
      "workspace_root": str(tmp_path),
      "branch": "new-feature",
      "create": True,
    })
    assert out.ok is True
    # Verify branch exists
    result = subprocess.run(["git", "branch", "--show-current"],
                           cwd=str(tmp_path), capture_output=True, text=True)
    assert result.stdout.strip() == "new-feature"

  def test_checkout_nonexistent_branch_fails(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = _git_checkout({"workspace_root": str(tmp_path), "branch": "nope"})
    assert out.ok is False

  def test_checkout_missing_branch_param(self, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = _git_checkout({"workspace_root": str(tmp_path)})
    assert out.ok is False
    assert "required" in out.message.lower()