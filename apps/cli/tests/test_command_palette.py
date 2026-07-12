"""Tests for TUI command palette."""
from __future__ import annotations

from apps.cli.src.tui.screens.command_palette import (
    BUILTIN_COMMANDS,
    CommandItem,
    filter_commands,
)


class TestCommandItem:
    """Tests for CommandItem dataclass."""

    def test_command_item_fields(self) -> None:
        item = CommandItem("test", "Test", "A test command", "general")
        assert item.id == "test"
        assert item.label == "Test"
        assert item.description == "A test command"
        assert item.category == "general"

    def test_command_item_label_repr(self) -> None:
        item = CommandItem("quit", "Quit", "Exit the app", "app")
        assert item.label == "Quit"

    def test_builtin_commands_count(self) -> None:
        assert len(BUILTIN_COMMANDS) == 8

    def test_builtin_commands_unique_ids(self) -> None:
        ids = [c.id for c in BUILTIN_COMMANDS]
        assert len(ids) == len(set(ids))

    def test_builtin_commands_have_required_fields(self) -> None:
        for cmd in BUILTIN_COMMANDS:
            assert cmd.id
            assert cmd.label
            assert cmd.description
            assert cmd.category

    def test_builtin_commands_categories(self) -> None:
        categories = {c.category for c in BUILTIN_COMMANDS}
        expected = {"session", "view", "model", "config", "help", "app"}
        assert categories == expected


class TestFilterCommands:
    """Tests for filter_commands function."""

    def test_empty_query_returns_all(self) -> None:
        result = filter_commands(BUILTIN_COMMANDS, "")
        assert len(result) == len(BUILTIN_COMMANDS)

    def test_filters_by_id(self) -> None:
        result = filter_commands(BUILTIN_COMMANDS, "quit")
        assert len(result) == 1
        assert result[0].id == "quit"

    def test_filters_by_label(self) -> None:
        result = filter_commands(BUILTIN_COMMANDS, "Help")
        assert len(result) == 1
        assert result[0].id == "help"

    def test_filters_by_description(self) -> None:
        result = filter_commands(BUILTIN_COMMANDS, "sidebar")
        ids = [c.id for c in result]
        assert "toggle_sidebar" in ids

    def test_filters_by_category(self) -> None:
        result = filter_commands(BUILTIN_COMMANDS, "session")
        ids = [c.id for c in result]
        assert "new_session" in ids
        assert "refresh_sessions" in ids

    def test_case_insensitive(self) -> None:
        r1 = filter_commands(BUILTIN_COMMANDS, "QUIT")
        r2 = filter_commands(BUILTIN_COMMANDS, "quit")
        assert len(r1) == len(r2)

    def test_no_match_returns_empty(self) -> None:
        result = filter_commands(BUILTIN_COMMANDS, "xyz_nonexistent_command")
        assert len(result) == 0
