"""Tests for the inline slash-command overlay widget."""
from __future__ import annotations

from apps.cli.src.tui.widgets.slash_overlay import (
    SLASH_COMMANDS,
    SlashCommand,
    filter_slash_commands,
    _render_command_row,
    CATEGORY_ICONS,
)


class TestSlashCommand:
  """Tests for SlashCommand dataclass."""

  def test_fields(self) -> None:
    cmd = SlashCommand("test", "Test", "A test", "general", "t", "X", "Ctrl+T")
    assert cmd.id == "test"
    assert cmd.label == "Test"
    assert cmd.description == "A test"
    assert cmd.category == "general"
    assert cmd.alias == "t"
    assert cmd.icon == "X"
    assert cmd.shortcut == "Ctrl+T"

  def test_defaults(self) -> None:
    cmd = SlashCommand("x", "X", "desc")
    assert cmd.category == "general"
    assert cmd.alias == ""
    assert cmd.icon == ">"
    assert cmd.shortcut == ""

  def test_builtin_commands_count(self) -> None:
    assert len(SLASH_COMMANDS) == 10

  def test_builtin_ids_unique(self) -> None:
    ids = [c.id for c in SLASH_COMMANDS]
    assert len(ids) == len(set(ids))

  def test_builtin_aliases_unique(self) -> None:
    aliases = [c.alias for c in SLASH_COMMANDS if c.alias]
    assert len(aliases) == len(set(aliases))

  def test_all_have_icons(self) -> None:
    for cmd in SLASH_COMMANDS:
      assert cmd.icon, f"{cmd.id} missing icon"


class TestFilterSlashCommands:
  """Tests for filter_slash_commands."""

  def test_empty_query_returns_all(self) -> None:
    assert len(filter_slash_commands(SLASH_COMMANDS, "")) == len(SLASH_COMMANDS)

  def test_filter_by_id(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "quit")
    assert len(result) == 1
    assert result[0].id == "quit"

  def test_filter_by_alias(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "q")
    ids = [c.id for c in result]
    assert "quit" in ids

  def test_filter_by_description(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "sidebar")
    ids = [c.id for c in result]
    assert "sidebar" in ids

  def test_filter_by_category(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "session")
    ids = [c.id for c in result]
    assert "new_session" in ids
    assert "refresh" in ids
    assert "compact" in ids

  def test_strips_leading_slash(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "/help")
    assert len(result) == 1
    assert result[0].id == "help"

  def test_case_insensitive(self) -> None:
    r1 = filter_slash_commands(SLASH_COMMANDS, "QUIT")
    r2 = filter_slash_commands(SLASH_COMMANDS, "quit")
    assert len(r1) == len(r2)

  def test_no_match(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "zzz_nonexistent")
    assert len(result) == 0


class TestRenderRow:
  """Tests for _render_command_row."""

  def test_contains_id_and_description(self) -> None:
    cmd = SlashCommand("quit", "Quit", "Exit the app", "app", icon="X", shortcut="Ctrl+Q")
    row = _render_command_row(cmd)
    assert "/quit" in row
    assert "Exit the app" in row
    assert "[Ctrl+Q]" in row
    assert "X" in row

  def test_alias_shown_when_present(self) -> None:
    cmd = SlashCommand("quit", "Quit", "Exit", "app", alias="q", icon="X")
    row = _render_command_row(cmd)
    assert "/q" in row

  def test_no_alias_when_empty(self) -> None:
    cmd = SlashCommand("clear", "Clear", "Clear chat", "view", icon="C")
    row = _render_command_row(cmd)
    # Should not have "//" or extra "/ "
    assert "//" not in row


class TestCategoryIcons:
  """Tests for CATEGORY_ICONS completeness."""

  def test_all_builtin_categories_covered(self) -> None:
    categories = {c.category for c in SLASH_COMMANDS}
    for cat in categories:
      assert cat in CATEGORY_ICONS, f"Missing icon for category: {cat}"
