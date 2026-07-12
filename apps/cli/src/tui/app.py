"""KCode Terminal User Interface — Textual application shell."""
from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from packages.core.src.config.loader import ModelProviderConfig
from packages.core.src.models.openai_compatible import OpenAICompatibleClient
from packages.core.src.tools.contracts import ToolRegistry
from packages.core.src.runtime.session import SessionStore
from packages.core.src.runtime.events import EventBus
from apps.cli.src.core.agent_runtime import CliAgentRuntime, AgentLoopConfig
from apps.cli.src.config.resolution import resolve_config
from apps.cli.src.tools.builtin_core import register_core_tools
from apps.cli.src.tools.builtin_readonly import register_readonly_tools

from .screens.main_screen import MainScreen


class KCodeTUI(App):
  """KCode Terminal User Interface."""

  TITLE = "KCode"
  SUB_TITLE = "AI Coding Assistant"

  BINDINGS = [
    Binding("ctrl+c", "quit", "Quit"),
    Binding("ctrl+n", "new_session", "New Session", show=True),
    Binding("ctrl+q", "quit", "Quit", show=False),
  ]

  def __init__(self) -> None:
    super().__init__()
    self._runtime: CliAgentRuntime | None = None

  def _create_agent_runtime(self) -> CliAgentRuntime:
    """Build the agent runtime from resolved config."""
    workspace_root = Path.cwd()
    config = resolve_config(workspace_root)

    model_client = OpenAICompatibleClient(
      ModelProviderConfig(
        base_url=config.model.base_url,
        api_key=config.model.api_key,
        timeout_seconds=config.model.timeout_seconds,
      )
    )

    tool_registry = ToolRegistry()
    register_core_tools(tool_registry)
    register_readonly_tools(tool_registry)

    session_store = SessionStore(
      Path.home() / ".kcode" / "sessions.sqlite"
    )

    bus = EventBus()

    return CliAgentRuntime(
      workspace_root=workspace_root,
      model_client=model_client,
      model_name=config.model.default_model or "gpt-4o",
      tool_registry=tool_registry,
      session_store=session_store,
      bus=bus,
      config=AgentLoopConfig(),
    )

  def on_mount(self) -> None:
    """Create runtime and push main screen after mount."""
    self._runtime = self._create_agent_runtime()
    self.push_screen(MainScreen(self._runtime))

  async def action_quit(self) -> None:
    """Quit the application."""
    self.exit()

  def action_new_session(self) -> None:
    """Forward to the active MainScreen."""
    screen = self.screen
    if isinstance(screen, MainScreen):
      screen.action_new_session()

