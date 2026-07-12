# <h1 align="center">KCode</h1>
<p align="center"><strong>Production-grade, cross-platform CLI coding agent</strong></p>
<p align="center">
  <img src="https://img.shields.io/badge/python-3.13+-blue.svg" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/tests-325-green.svg" alt="Tests">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform">
</p>

---

KCode is a Python-native CLI coding agent with **streaming**, **tool safety**, **session persistence**, and **MCP integration**. It draws design inspiration from OpenCode, Crush, Aider, and OpenHands.

## Features

- **Streaming-first**: Real-time token and tool-call events via SSE
- **Tool safety model**: 4-tier safety classes (read/write/system/network) with approval gating
- **Session persistence**: SQLite-backed sessions with full message and tool-run history
- **MCP integration**: Stdio transport, tool bridging, safety heuristics
- **Multi-provider**: OpenAI-compatible API client with automatic model discovery
- **Context management**: tiktoken-aware token counting with budget enforcement
- **Cross-platform**: Windows, macOS, Linux — PowerShell and bash

## Quick Start

```bash
# Install
conda activate expr
pip install -e .

# Configure
mkdir -p ~/.config/kcode
cat > ~/.config/kcode/config.yaml << 'EOF'
provider:
  name: mimo
  base_url: https://api.xiaomimimo.com/v1
  api_key: YOUR_API_KEY
  models:
    default:
      - mimo-v2-pro
      - mimo-v2-flash
    reasoning:
      - mimo-v2-pro
    fast:
      - mimo-v2-flash
model:
  name: mimo-v2-pro
  max_tokens: 16384
  temperature: 0.0
  timeout: 120
  max_retries: 3
tools:
  approval_mode: ask
  commands:
    allowed:
      - "*"
  timeouts:
    command: 300
    read_file: 30
  limits:
    max_file_bytes: 1048576
debug: false
EOF

# Run
kcode chat "Write a fibonacci function"
```

## Commands

| Command | Description |
|---------|-------------|
| `kcode chat [message]` | Single-shot or interactive agent chat |
| `kcode init` | Bootstrap `.kcode/` workspace |
| `kcode doctor` | Check runtime prerequisites |
| `kcode config show` | Print resolved configuration |
| `kcode config validate` | Validate config sources |
| `kcode config list-models` | List available models from provider |
| `kcode sessions list` | List past sessions |
| `kcode sessions resume <id>` | Resume a past session |

## Chat Options

```bash
kcode chat [OPTIONS] [MESSAGE]

Options:
  -w, --workspace PATH    Workspace directory
  -m, --model TEXT        Model override
  -p, --provider TEXT     Provider override
  -a, --approval TEXT     Approval mode: ask or auto
  --max-steps INTEGER     Max agent loop steps
```

## Architecture

```
packages/core/          # Reusable agent SDK (zero CLI deps)
  config/               # Pydantic config schemas
  context/              # Token counting, budget management
  models/               # ModelClient ABC, OpenAI-compatible client
  runtime/              # AgentRuntime, SessionStore, EventBus
  tools/                # ToolRegistry, MCP bridge

apps/cli/               # CLI adapter (Typer + Rich)
  commands/             # chat, init, doctor, config, sessions
  config/               # Multi-source config resolution
  core/                 # CliAgentRuntime
  tools/                # Built-in tools (read, write, edit, search, git, todo)
```

## Tool Safety

| Class | Tools | Approval |
|-------|-------|----------|
| `read` | read_file, list_files, search_code, git_status | Auto |
| `write` | create_file, edit_file, git_commit, todo_write | Ask/Auto |
| `system` | run_command | Ask/Auto |
| `network` | (future: web_fetch) | Ask/Auto |

## E2E Validation

| Test | Description | Result |
|------|-------------|--------|
| Fibonacci | Create module + tests, run pytest | 6/6 passed |
| Todo App | Multi-file scaffolding | All files created |
| Debug Fix | Read broken code, diagnose, fix | Bug fixed |
| 2048 Game | Complex HTML/JS/CSS game | Full game with touch |

## Development

```bash
# Setup
conda activate expr
pip install -e ".[dev]"

# Quality checks
ruff check .
mypy apps packages
python -m pytest -v

# Run CLI
kcode --version
kcode doctor
```

## Documentation

- [AGENTS.md](AGENTS.md) — Engineering guide and architecture reference
- [docs/m1/M1-spec.md](docs/m1/M1-spec.md) — M1 milestone specification
- [docs/research/](docs/research/) — Comparative analysis and design patterns

## License

MIT
