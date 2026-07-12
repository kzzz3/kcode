"""CLI: kcode init."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from rich import print as rprint
from rich.prompt import Prompt

_KCODE_DIR = ".kcode"
_CONFIG_FILE = "config.yaml"

# Pre-defined provider profiles for quick selection.
_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI (GPT-4o / GPT-4.1)",
        "provider_type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
    },
    "deepseek": {
        "label": "DeepSeek (deepseek-chat / deepseek-coder)",
        "provider_type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "anthropic": {
        "label": "Anthropic Claude (via OpenAI-compatible proxy)",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:8080/v1",
        "default_model": "claude-sonnet-4-20250514",
    },
    "ollama": {
        "label": "Ollama (local, llama3 / qwen2.5)",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_model": "llama3",
    },
    "mimo": {
        "label": "MiMo (Xiaomi MiMo-v2.5)",
        "provider_type": "openai_compatible",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "default_model": "mimo-v2.5-pro",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible endpoint)",
        "provider_type": "openai_compatible",
        "base_url": "",
        "default_model": "",
    },
}


def _print_profile_menu() -> None:
    """Display provider profiles as a numbered menu."""
    rprint("\n[bold cyan]Select a provider profile:[/bold cyan]")
    for i, (key, profile) in enumerate(_PROVIDER_PROFILES.items(), 1):
        rprint(f"  [bold]{i}.[/bold] {profile['label']}  [dim]({profile['base_url']})[/dim]")
    rprint()


def _select_profile() -> dict[str, Any]:
    """Prompt user to pick a profile; return the selected profile dict."""
    _print_profile_menu()
    keys = list(_PROVIDER_PROFILES.keys())
    choice = Prompt.ask(
        "Profile number",
        choices=[str(i) for i in range(1, len(keys) + 1)],
        default="1",
    )
    return _PROVIDER_PROFILES[keys[int(choice) - 1]]


def _try_fetch_models(base_url: str, api_key: str) -> list[str]:
    """Try to fetch model list from GET /v1/models. Returns sorted model IDs or empty list."""
    import httpx

    try:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = httpx.get(f"{base_url}/models", headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        models = [entry.get("id", "") for entry in data.get("data", []) if entry.get("id")]
        return sorted(models)
    except Exception:
        return []


def _pick_model(base_url: str, api_key: str, default_model: str) -> str:
    """Auto-fetch model list and let user pick, or fall back to manual entry."""
    rprint("[dim]Fetching model list from provider...[/dim]")
    models = _try_fetch_models(base_url, api_key)

    if not models:
        rprint("[yellow]Could not fetch model list. Enter model name manually.[/yellow]")
        return Prompt.ask("Default model", default=default_model)

    rprint(f"[green]Found {len(models)} model(s):[/green]")
    for i, mid in enumerate(models, 1):
        marker = " [dim](default)[/dim]" if mid == default_model else ""
        rprint(f"  [bold]{i}.[/bold] {mid}{marker}")

    rprint()
    choices = [str(i) for i in range(1, len(models) + 1)]
    # Default to the index of default_model if present, otherwise "1"
    default_idx = "1"
    if default_model in models:
        default_idx = str(models.index(default_model) + 1)

    choice = Prompt.ask(
        "Select model (number) or type a model name",
        choices=choices,
        default=default_idx,
    )
    try:
        return models[int(choice) - 1]
    except (ValueError, IndexError):
        return choice


def _prompt_config(profile: dict[str, Any]) -> dict[str, Any]:
    """Walk the user through provider configuration."""
    model_section: dict[str, Any] = {
        "provider_type": profile["provider_type"],
    }

    # base_url
    default_url = profile["base_url"]
    base_url = Prompt.ask("API base URL", default=default_url) if default_url else Prompt.ask("API base URL")
    model_section["base_url"] = base_url

    # api_key
    api_key = Prompt.ask("API key (leave empty for local/no-auth)", default="")
    if api_key:
        model_section["api_key"] = api_key

    # default_model — auto-fetch list if possible
    default_model = profile["default_model"]
    model = _pick_model(base_url, api_key, default_model)
    model_section["default_model"] = model

    return {"model": model_section}


def _write_config(target: Path, config_data: dict[str, Any]) -> Path:
    """Write config.yaml into .kcode/ directory."""
    kcode_dir = target / _KCODE_DIR
    kcode_dir.mkdir(exist_ok=True)
    config_path = kcode_dir / _CONFIG_FILE
    config_path.write_text(
        yaml.dump(config_data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path


def run_init(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Target workspace path."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive provider setup wizard."),
) -> None:
    """Bootstrap a workspace with optional interactive config."""
    target = path.resolve()
    target.mkdir(parents=True, exist_ok=True)

    # Always create workspace scaffolding
    kcode_dir = target / _KCODE_DIR
    kcode_dir.mkdir(exist_ok=True)
    readme = target / "kcode.workspace.md"
    if not readme.exists():
        readme.write_text("# KCode Workspace\n\nInitialized workspace for KCode CLI.\n", encoding="utf-8")

    rprint(f"[green]Initialized workspace:[/green] {target}")

    if interactive:
        rprint("\n[bold]Provider Configuration Wizard[/bold]")
        rprint("[dim]Press Enter to accept defaults.[/dim]\n")

        profile = _select_profile()
        config_data = _prompt_config(profile)

        config_path = _write_config(target, config_data)
        rprint(f"\n[green]Config written:[/green] {config_path}")

        # Show summary
        model_cfg = config_data["model"]
        rprint(f"  Provider:  [cyan]{model_cfg['provider_type']}[/cyan]")
        rprint(f"  Base URL:  [cyan]{model_cfg['base_url']}[/cyan]")
        rprint(f"  Model:     [cyan]{model_cfg['default_model']}[/cyan]")
        masked_key = model_cfg.get("api_key", "")
        if masked_key:
            rprint(f"  API Key:   [cyan]{masked_key[:6]}...{masked_key[-4:]}[/cyan]")

        rprint("\n[green]Done![/green] Run [bold]kcode chat[/bold] to start.")
    else:
        rprint("[dim]Tip: run [bold]kcode init --interactive[/bold] to configure providers.[/dim]")
