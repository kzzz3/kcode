"""Tests for TUI command palette widget."""
from __future__ import annotations

from apps.cli.src.tui.screens.command_palette import (
  CommandItem,
  CommandPalette,
  BUILTIN_COMMANDS,
  filter_commands,
)
from apps.cli.src.tui.widgets.input_area import InputArea


def test_command_item_fields():
  item = CommandItem(id="test_id", label="Test Label", description="A test command")
  assert item.id == "test_id"
  assert item.label == "Test Label"
  assert item.description == "A test command"


def test_builtin_commands_contains_expected():
  ids = [c.id for c in BUILTIN_COMMANDS]
  assert "new_session" in ids
  assert "refresh_sessions" in ids
  assert "toggle_sidebar" in ids
  assert "quit" in ids


def test_builtin_commands_have_labels():
  for cmd in BUILTIN_COMMANDS:
    assert cmd.label, f"{cmd.id} missing label"
    assert cmd.description, f"{cmd.id} missing description"


def test_input_area_open_command_palette_message():
  msg = InputArea.OpenCommandPalette()
  assert isinstance(msg, InputArea.OpenCommandPalette)


def test_filter_commands_returns_all_on_empty():
  results = filter_commands(BUILTIN_COMMANDS, "")
  assert len(results) == len(BUILTIN_COMMANDS)


def test_filter_commands_partial_match():
  results = filter_commands(BUILTIN_COMMANDS, "new")
  assert len(results) == 1
  assert results[0].id == "new_session"


def test_filter_commands_case_insensitive():
  results = filter_commands(BUILTIN_COMMANDS, "QUIT")
  assert len(results) == 1
  assert results[0].id == "quit"


def test_filter_commands_no_match():
  results = filter_commands(BUILTIN_COMMANDS, "zzzznonexistent")
  assert len(results) == 0


def test_filter_commands_description_match():
  results = filter_commands(BUILTIN_COMMANDS, "refresh")
  assert any(r.id == "refresh_sessions" for r in results)


def test_builtin_commands_all_unique_ids():
  ids = [c.id for c in BUILTIN_COMMANDS]
  assert len(ids) == len(set(ids)), "Command IDs must be unique"
