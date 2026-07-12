"""Tests for the inline slash-command overlay widget."""
from __future__ import annotations

from apps.cli.src.tui.widgets.slash_overlay import (
    SLASH_COMMANDS,
    SlashCommand,
    filter_slash_commands,
    group_by_category,
    CATEGORY_META,
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
    assert len(SLASH_COMMANDS) == 13

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
    assert "new" in ids
    assert "refresh" in ids
    assert "compact" in ids

  def test_strips_leading_slash(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "/quit")
    assert len(result) == 1
    assert result[0].id == "quit"

  def test_case_insensitive(self) -> None:
    r1 = filter_slash_commands(SLASH_COMMANDS, "QUIT")
    r2 = filter_slash_commands(SLASH_COMMANDS, "quit")
    assert len(r1) == len(r2)

  def test_no_match(self) -> None:
    result = filter_slash_commands(SLASH_COMMANDS, "zzz_nonexistent")
    assert len(result) == 0

  def test_multi_token_filter(self) -> None:
    """Multi-word queries use AND logic."""
    result = filter_slash_commands(SLASH_COMMANDS, "chat clear")
    ids = [c.id for c in result]
    assert "clear" in ids


class TestGroupByCategory:
  """Tests for group_by_category."""

  def test_groups_match_category_meta(self) -> None:
    groups = group_by_category(SLASH_COMMANDS)
    group_labels = [label for label, _, _ in groups]
    # All CATEGORY_META labels should appear
    meta_labels = [label for _, label, _ in CATEGORY_META]
    for label in meta_labels:
      assert label in group_labels, f"Missing category group: {label}"

  def test_each_group_has_commands(self) -> None:
    groups = group_by_category(SLASH_COMMANDS)
    for label, icon, cmds in groups:
      assert len(cmds) > 0, f"Category {label} is empty"

  def test_total_commands_preserved(self) -> None:
    groups = group_by_category(SLASH_COMMANDS)
    total = sum(len(cmds) for _, _, cmds in groups)
    assert total == len(SLASH_COMMANDS)


class TestCategoryMeta:
  """Tests for CATEGORY_META completeness."""

  def test_all_builtin_categories_covered(self) -> None:
    categories = {c.category for c in SLASH_COMMANDS}
    meta_keys = {key for key, _, _ in CATEGORY_META}
    for cat in categories:
      assert cat in meta_keys, f"Missing meta for category: {cat}"



class TestCustomCommandInjection:
    def test_set_custom_commands_adds_items(self) -> None:
        from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
        overlay = SlashOverlay()
        custom = [SlashCommand("user:review", "Review", "Run review", category="Custom", icon="#", is_custom=True)]
        overlay.set_custom_commands(custom)
        assert any(c.id == "user:review" for c in overlay._commands)


class TestIconAscii:
    def test_all_icons_ascii(self) -> None:
        for cmd in SLASH_COMMANDS:
            assert cmd.icon.isascii(), f"{cmd.id} icon not ASCII"
class TestArgumentDialog:
  """Tests for SlashOverlay.ArgumentDialog static methods."""

  def test_extract_placeholders_basic(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.extract_placeholders("Hello $NAME!")
    assert result == ["NAME"]

  def test_extract_placeholders_multiple(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.extract_placeholders(
      "Project $PROJECT in $DIR"
    )
    assert result == ["PROJECT", "DIR"]

  def test_extract_placeholders_dedup(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.extract_placeholders("$A and $A")
    assert result == ["A"]

  def test_extract_placeholders_none(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.extract_placeholders("No placeholders")
    assert result == []

  def test_extract_placeholders_uppercase_only(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.extract_placeholders("$lower $UPPER")
    assert result == ["UPPER"]

  def test_extract_placeholders_with_digits(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.extract_placeholders("$NAME2 test")
    assert result == ["NAME2"]

  def test_apply_arguments_single(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.apply_arguments(
      "Hello $NAME!", {"NAME": "World"}
    )
    assert result == "Hello World!"

  def test_apply_arguments_multiple(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.apply_arguments(
      "$A + $B", {"A": "1", "B": "2"}
    )
    assert result == "1 + 2"

  def test_apply_arguments_none(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    result = SlashOverlay.ArgumentDialog.apply_arguments(
      "No args here", {}
    )
    assert result == "No args here"

  def test_extract_and_apply_roundtrip(self) -> None:
    from apps.cli.src.tui.widgets.slash_overlay import SlashOverlay
    template = "Write a $LANG function for $TASK"
    names = SlashOverlay.ArgumentDialog.extract_placeholders(template)
    assert names == ["LANG", "TASK"]
    result = SlashOverlay.ArgumentDialog.apply_arguments(
      template, {"LANG": "Python", "TASK": "sorting"}
    )
    assert result == "Write a Python function for sorting"