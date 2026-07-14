"""Tests for TUI responsive layout (Milestone C Task 6).

Verifies that the main screen adapts at three breakpoints:
  narrow (<90 cols), medium (90-139 cols), wide (>=140 cols).
Uses Textual async test pilot for proper widget tree testing.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ── Helpers ──────────────────────────────────────────────────────

def _make_runtime_stub():
  """Create a minimal runtime stub for screen construction."""
  rt = MagicMock()
  rt._workspace_root = Path.cwd()
  rt._model_name = "test-model"
  rt.config = MagicMock()
  rt.config.approval_mode = "auto"
  return rt


# ── Responsive class tests (pure logic, no App needed) ──────────

class TestResponsiveClassLogic:
  """Test _apply_responsive_class directly via size mock."""

  def _make_screen(self):
    from apps.cli.src.tui.screens.main_screen import MainScreen
    screen = MainScreen(_make_runtime_stub())
    return screen

  def test_narrow_at_80(self):
    screen = self._make_screen()
    # Mock size as a simple object with width attribute
    mock_size = MagicMock()
    mock_size.width = 80
    screen._size = mock_size
    # Patch the size property to use our mock
    type(screen).size = property(lambda self: self._size)
    screen._apply_responsive_class()
    assert "narrow" in screen.classes
    assert "medium" not in screen.classes
    assert "wide" not in screen.classes

  def test_medium_at_100(self):
    screen = self._make_screen()
    mock_size = MagicMock()
    mock_size.width = 100
    screen._size = mock_size
    type(screen).size = property(lambda self: self._size)
    screen._apply_responsive_class()
    assert "medium" in screen.classes
    assert "narrow" not in screen.classes
    assert "wide" not in screen.classes

  def test_wide_at_160(self):
    screen = self._make_screen()
    mock_size = MagicMock()
    mock_size.width = 160
    screen._size = mock_size
    type(screen).size = property(lambda self: self._size)
    screen._apply_responsive_class()
    assert "wide" in screen.classes
    assert "narrow" not in screen.classes
    assert "medium" not in screen.classes


# ── Structure tests via Pilot ────────────────────────────────────

@pytest.mark.asyncio
async def test_layout_has_key_widgets():
  """Pilot test: MainScreen mounts with expected widget IDs."""
  from textual.app import App
  from apps.cli.src.tui.screens.main_screen import MainScreen

  class TestApp(App):
    def on_mount(self):
      self.push_screen(MainScreen(_make_runtime_stub()))

  async with TestApp().run_test(size=(120, 30)) as pilot:
    screen = pilot.app.screen
    # Check key container IDs exist in the compose tree
    assert screen.query("#workspace-bar")
    assert screen.query("#main-body")
    assert screen.query("#chat")
    assert screen.query("#activity-rail")
    assert screen.query("#composer-dock")
    assert screen.query("#status")


@pytest.mark.asyncio
async def test_narrow_hides_rail():
  """At 80 cols the activity rail should be hidden."""
  from textual.app import App
  from apps.cli.src.tui.screens.main_screen import MainScreen

  class TestApp(App):
    def on_mount(self):
      self.push_screen(MainScreen(_make_runtime_stub()))

  async with TestApp().run_test(size=(80, 24)) as pilot:
    screen = pilot.app.screen
    rail = screen.query_one("#activity-rail")
    assert rail.display is False


@pytest.mark.asyncio
async def test_wide_shows_rail():
  """At 160 cols the activity rail should be visible."""
  from textual.app import App
  from apps.cli.src.tui.screens.main_screen import MainScreen

  class TestApp(App):
    def on_mount(self):
      self.push_screen(MainScreen(_make_runtime_stub()))

  async with TestApp().run_test(size=(160, 40)) as pilot:
    screen = pilot.app.screen
    rail = screen.query_one("#activity-rail")
    assert rail.display is True


@pytest.mark.asyncio
async def test_composer_visible_at_all_sizes():
  """Composer dock must be visible at all three breakpoints."""
  from textual.app import App
  from apps.cli.src.tui.screens.main_screen import MainScreen

  class TestApp(App):
    def __init__(self, size):
      super().__init__()
      self._test_size = size
    def on_mount(self):
      self.push_screen(MainScreen(_make_runtime_stub()))

  for w, h in [(80, 24), (120, 30), (160, 40)]:
    async with TestApp((w, h)).run_test(size=(w, h)) as pilot:
      screen = pilot.app.screen
      dock = screen.query_one("#composer-dock")
      assert dock.display is True, f"Composer hidden at {w}x{h}"


@pytest.mark.asyncio
async def test_transcript_tall_enough():
  """Chat area height must be > 8 lines at all sizes."""
  from textual.app import App
  from apps.cli.src.tui.screens.main_screen import MainScreen

  class TestApp(App):
    def on_mount(self):
      self.push_screen(MainScreen(_make_runtime_stub()))

  for w, h in [(80, 24), (120, 30), (160, 40)]:
    async with TestApp().run_test(size=(w, h)) as pilot:
      screen = pilot.app.screen
      chat = screen.query_one("#chat")
      assert chat.size.height > 8, f"Chat too short at {w}x{h}: {chat.size.height}"


# ── WorkspaceBar tests ───────────────────────────────────────────

class TestWorkspaceBar:
  """Test WorkspaceBar renders info via update()."""

  def test_set_model(self):
    from apps.cli.src.tui.screens.main_screen import WorkspaceBar
    bar = WorkspaceBar(Path("/tmp/test"), model="old", id="test")
    bar._refresh = MagicMock()
    bar.set_model("new-model")
    assert bar._model == "new-model"
    bar._refresh.assert_called_once()

  def test_set_session(self):
    from apps.cli.src.tui.screens.main_screen import WorkspaceBar
    bar = WorkspaceBar(Path("/tmp/test"), id="test")
    bar._refresh = MagicMock()
    bar.set_session("My Session")
    assert bar._session_title == "My Session"
    bar._refresh.assert_called_once()
