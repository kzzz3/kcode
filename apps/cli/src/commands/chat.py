"""CLI: kcode chat — single-shot and interactive modes with streaming."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rich import print as rprint
from rich.prompt import Confirm
import typer

from apps.cli.src.config.resolution import resolve_config
from apps.cli.src.core.agent_runtime import AgentLoopConfig, CliAgentRuntime
from packages.core.src.config.loader import ApprovalMode
from packages.core.src.models.interfaces import ChunkType, StreamChunk
from packages.core.src.runtime.contracts import AgentSnapshot
from packages.core.src.runtime.events import EventBus
from packages.core.src.runtime.session import SessionStore
from packages.core.src.tools.contracts import ToolRegistry
from apps.cli.src.tools.builtin_core import register_core_tools
from apps.cli.src.tools.builtin_readonly import register_readonly_tools
from packages.core.src.models.openai_compatible import OpenAICompatibleClient


# Approximate cost per 1M tokens for common model families
_COST_TABLE: dict[str, tuple[float, float]] = {
  "gpt-4o": (2.50, 10.00),
  "gpt-4-turbo": (10.00, 30.00),
  "gpt-3.5-turbo": (0.50, 1.50),
  "o1": (15.00, 60.00),
  "o3": (10.00, 40.00),
  "deepseek": (0.27, 1.10),
  "claude-3-opus": (15.00, 75.00),
  "claude-3-sonnet": (3.00, 15.00),
}




def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
  """Estimate cost in USD for a given model and token counts."""
  model_lower = model.lower()
  for prefix, (input_cost, output_cost) in _COST_TABLE.items():
    if prefix in model_lower:
      return (prompt_tokens * input_cost + completion_tokens * output_cost) / 1_000_000
  return None


def _format_usage_line(usage: dict[str, Any], model: str) -> str:
  """Format a compact usage/cost line for terminal display."""
  prompt_tok = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
  completion_tok = usage.get("completion_tokens") or usage.get("output_tokens") or 0
  total_tok = prompt_tok + completion_tok
  cost = _estimate_cost(model, prompt_tok, completion_tok)
  parts = [f"tokens: {prompt_tok:,} in / {completion_tok:,} out ({total_tok:,} total)"]
  if cost is not None:
    parts.append(f"~${cost:.4f}")
  return " | ".join(parts)


def _approval_handler(mode: ApprovalMode) -> Any:
  """Create an approval callback based on the approval mode.

  - ``manual``: prompt the user for every sensitive tool call.
  - ``auto``: approve all tool calls without prompting.
  """
  def handler(tool_name: str, safety_class: str, payload: dict[str, Any]) -> bool:
    if mode == ApprovalMode.auto:
      return True
    # Manual mode - prompt user with context
    rprint(f"[yellow]Approval required:[/yellow] {tool_name} ({safety_class})")
    preview_args = {k: (v if k != "content" else str(v)[:80] + "..." if len(str(v)) > 80 else v) for k, v in payload.items() if k not in ("workspace_root", "allowlist", "blocklist")}
    if preview_args:
      rprint(f"[dim]  args: {preview_args}[/dim]")
    return Confirm.ask("Allow?", default=False)
  return handler


def _stream_to_terminal(chunks: Any, model: str = "") -> dict[str, Any]:
  """Consume a step_stream() iterator, printing text deltas and tool status.

  Returns metadata dict with final state info.
  """
  text_buffer: list[str] = []
  tool_call_names: dict[str, str] = {}
  usage: dict[str, Any] = {}
  final_snapshot: AgentSnapshot | None = None

  for item in chunks:
    if isinstance(item, AgentSnapshot):
      final_snapshot = item
      continue

    chunk: StreamChunk = item
    if chunk.type == ChunkType.TEXT:
      text_buffer.append(chunk.delta)
      print(chunk.delta, end="", flush=True)
    elif chunk.type == ChunkType.TOOL_CALL_START:
      tool_call_names[chunk.tool_call_id] = chunk.tool_name
      rprint(f"\n[dim]tool: [bold]{chunk.tool_name}[/bold]...[/dim]", end="")
    elif chunk.type == ChunkType.TOOL_CALL_ARGS:
      pass
    elif chunk.type == ChunkType.TOOL_CALL_END:
      if chunk.delta:
        status = "ok" if not chunk.delta.startswith("Tool error") else "err"
        rprint(f" {status}")
      else:
        rprint(" ok")
    elif chunk.type == ChunkType.USAGE:
      usage = chunk.usage
    elif chunk.type == ChunkType.DONE:
      pass

  if text_buffer:
    print()

  # Display usage/cost line
  if usage:
    rprint(f"[dim]{_format_usage_line(usage, model)}[/dim]")

  # Display context utilization if available
  if final_snapshot is not None:
    util = final_snapshot.metadata.get("context_utilization")
    if util is not None and util > 0.5:
      color = "green" if util < 0.7 else "yellow" if util < 0.85 else "red"
      rprint(f"[dim][{color}]context: {util:.0%} used[/{color}][/dim]")

  return {
    "text": "".join(text_buffer),
    "usage": usage,
    "snapshot": final_snapshot,
  }


def run_chat(
    message: str | None = typer.Argument(None, help="Optional single-shot message. Omit to enter interactive mode."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override model name."),
    max_steps: int = typer.Option(6, "--max-steps", help="Maximum agent loop steps."),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming output."),
    approval_mode: ApprovalMode = typer.Option(
      ApprovalMode.auto,
      "--approval-mode",
      "-a",
      help="Tool approval policy: 'manual' prompts for sensitive calls, 'auto' approves all.",
    ),
) -> None:
    """Chat with the KCode agent."""
    config = resolve_config(workspace.resolve(), overrides={"workspace_root": str(workspace.resolve())})
    model_name = model or config.model.default_model
    if not model_name:
      rprint("[red]No model configured. Set model.default_model in config or pass --model.[/red]")
      raise typer.Exit(code=1)

    registry = ToolRegistry()
    register_readonly_tools(registry)
    register_core_tools(registry)
    store = SessionStore(workspace.resolve() / ".kcode" / "sessions.sqlite")
    try:
      # Merge CLI flag with config-level approval_mode (CLI wins if non-default)
      effective_approval = approval_mode
      config_approval = getattr(config.tools, "approval_mode", None)
      if config_approval is not None and approval_mode == ApprovalMode.auto:
        effective_approval = config_approval

      runtime = CliAgentRuntime(
        workspace_root=workspace.resolve(),
        model_client=OpenAICompatibleClient(config.model),
        model_name=model_name,
        tool_registry=registry,
        session_store=store,
        bus=EventBus(),
        config=AgentLoopConfig(
          max_steps=max_steps,
          approval_mode=effective_approval.value,
        ),
        on_approve=_approval_handler(effective_approval),
      )

      if message is not None:
        _single_shot(runtime, message, no_stream, model_name)
        return

      _interactive_loop(runtime, no_stream, model_name)
    finally:
      store.close()


def _single_shot(runtime: CliAgentRuntime, message: str, no_stream: bool, model: str) -> None:
  """Process a single message and exit."""
  if no_stream:
    snapshot = runtime.step(message)
    rprint(f"[cyan]state:[/cyan] {snapshot.state.value}")
    rprint(f"[cyan]session:[/cyan] {snapshot.metadata.get('session_id')}")
    if snapshot.messages:
      rprint(snapshot.messages[-1].get("content"))
    # Show usage from snapshot metadata
    token_count = snapshot.metadata.get("token_count")
    if token_count:
      rprint(f"[dim]context tokens: {token_count:,}[/dim]")
  else:
    result = _stream_to_terminal(runtime.step_stream(message), model)
    snap: AgentSnapshot | None = result.get("snapshot")
    if snap is not None:
      rprint(f"\n[dim]state: {snap.state.value} | session: {snap.metadata.get('session_id')}[/dim]")


def _interactive_loop(runtime: CliAgentRuntime, no_stream: bool, model: str) -> None:
  """Run the interactive REPL."""
  rprint("[green]Entering interactive mode. Type 'exit' to quit.[/green]")
  while True:
    try:
      user_input = input("\nyou> ").strip()
    except (EOFError, KeyboardInterrupt):
      rprint("\n[green]Goodbye.[/green]")
      break
    if not user_input:
      continue
    if user_input.lower() in {"exit", "quit"}:
      rprint("[green]Goodbye.[/green]")
      break

    if no_stream:
      snapshot = runtime.step(user_input)
      rprint(f"[cyan]state:[/cyan] {snapshot.state.value}")
      if snapshot.messages:
        rprint(snapshot.messages[-1].get("content"))
      token_count = snapshot.metadata.get("token_count")
      if token_count:
        rprint(f"[dim]context tokens: {token_count:,}[/dim]")
    else:
      result = _stream_to_terminal(runtime.step_stream(user_input), model)
      snap: AgentSnapshot | None = result.get("snapshot")
      if snap is not None:
        rprint(f"[dim]state: {snap.state.value}[/dim]")


