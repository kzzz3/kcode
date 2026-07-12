"""Tests for custom commands loader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from apps.cli.src.tui.utils.custom_commands import (
    load_all_custom_commands,
    load_project_commands,
    _load_commands_from_dir,
)


class TestCustomCommandParsing:
    """Test CustomCommand dataclass and parsing."""

    def test_basic_command(self, tmp_path: Path) -> None:
        md = "# Review\nReview the code for issues"
        (tmp_path / "review.md").write_text(md, encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert len(cmds) == 1
        assert cmds[0].id == "user:review"
        assert cmds[0].title == "Review"
        assert cmds[0].source == "user"
        assert cmds[0].has_arguments is False

    def test_command_with_arguments(self, tmp_path: Path) -> None:
        md = "# Fix Bug\nFix the bug $ISSUE_ID"
        (tmp_path / "fix.md").write_text(md, encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert cmds[0].has_arguments is True
        assert "ISSUE_ID" in cmds[0].argument_names

    def test_empty_directory(self, tmp_path: Path) -> None:
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert cmds == []

    def test_project_commands(self, tmp_path: Path) -> None:
        md = "# Lint\nRun ruff check"
        (tmp_path / ".kcode" / "commands").mkdir(parents=True)
        (tmp_path / ".kcode" / "commands" / "lint.md").write_text(md, encoding="utf-8")
        cmds = load_project_commands(tmp_path)
        assert cmds[0].source == "project"
        assert cmds[0].id == "project:lint"


    def test_nested_dir_ids(self, tmp_path: Path) -> None:
        d = tmp_path / "git"
        d.mkdir()
        (d / "review.md").write_text("# Review\nCheck changes", encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "project")
        assert any(c.id == "project:git:review" for c in cmds)

    def test_oversize_file_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "big.md").write_text("# Big\n" + ("x" * (128 * 1024 + 1)), encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert cmds == []

    def test_argument_names_list_not_none(self, tmp_path: Path) -> None:
        (tmp_path / "fix.md").write_text("# Fix\nFix $ISSUE_ID", encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert isinstance(cmds[0].argument_names, list)


    def test_file_path_populated(self, tmp_path: Path) -> None:
        md = "# Review\nCheck changes"
        p = tmp_path / "review.md"
        p.write_text(md, encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert cmds[0].file_path == p

    def test_utf8_sig_encoding_fallback(self, tmp_path: Path) -> None:
        md = "# Review\nCheck changes"
        p = tmp_path / "review.md"
        p.write_bytes(md.encode("utf-8-sig"))
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert len(cmds) == 1
        assert cmds[0].title == "Review"

    def test_argument_names_are_list_instances(self, tmp_path: Path) -> None:
        md = "# Fix\nFix $ISSUE_ID in $PROJECT"
        (tmp_path / "fix.md").write_text(md, encoding="utf-8")
        cmds = _load_commands_from_dir(tmp_path, "user")
        assert isinstance(cmds[0].argument_names, list)
        assert cmds[0].argument_names == ["ISSUE_ID", "PROJECT"]
    def test_combined(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user_cmds"
        user_dir.mkdir()
        (user_dir / "a.md").write_text("# A\nCmd A", encoding="utf-8")
        proj_dir = tmp_path / "proj" / ".kcode" / "commands"
        proj_dir.mkdir(parents=True)
        (proj_dir / "b.md").write_text("# B\nCmd B", encoding="utf-8")
        with patch(
            "apps.cli.src.tui.utils.custom_commands.load_user_commands",
            return_value=_load_commands_from_dir(user_dir, "user"),
        ):
            cmds = load_all_custom_commands(tmp_path / "proj")
        assert len(cmds) == 2
        ids = [c.id for c in cmds]
        assert "user:a" in ids
        assert "project:b" in ids