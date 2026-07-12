# AGENTS.md instructions for F:\Project\kcode

<INSTRUCTIONS>
# KCode — Agent Engineering Guide

## Project Overview

KCode is a **production-grade, cross-platform CLI coding agent** written in Python.
It draws design inspiration from OpenCode (Go/BubbleTea/MCP), Crush (Charm),
Aider (repo-map, git-aware diffs), and OpenHands (agent-server separation).

**Core design pillars:**
1. Precision over breadth — excellent single-repo coding agent first.
2. Safe by default — commands, file mutations, network use are observable and controllable.
3. Layered extensibility — tools, models, storage, and UI are all replaceable.
4. Testable from day one — pure core with isolated IO/runtime adapters.

---

## Implementation Status

| Area | Status | Notes |
|---|---|---|
| Repo bootstrap / docs / structure | Done | Monorepo layout exists and is stable. |
| Core CLI, config, doctor, init | Done | `kcode`, `kcode init`, `kcode doctor`, `kcode config` implemented. |
| Model abstraction (OpenAI adapter) | Done | Provider-agnostic `ModelClient` ABC + OpenAI-compatible client. |
| Agent loop + core tools | Done | `CliAgentRuntime` with tool dispatch + streaming implemented. |
| Edit workflow + tool safety | Done | read/write/system/network classes; approval gating exists. |
| Session persistence | Done | SQLite/WAL session + message + tool-run persistence. |
| Token counting + context budget | Done | tiktoken-aware counting with fallback + `ContextBudget`. |
| MCP adapter | Done | `McpToolProvider` ABC + `McpStdioProvider` + bridge + config. |
| Packaging/CI | Done | Entry point, GitHub Actions CI matrix (Win/Mac/Linux). |
| Integration test suite | Done | 325 tests passing; ruff clean; coverage ~85%. |
| E2E validation | Done | Fibonacci pytest, multi-file scaffolding, 2048 game all passed. |
| Desktop surface | Future | Wrap core runtime with GUI shell. |

---

## Architecture

### Monorepo Layout

```
F:\Project\kcode\
├─ packages/
│  └─ core/                 # Reusable agent SDK — zero CLI/UI deps
│     └─ src/
│        ├─ config/         # Pydantic config schemas (AppConfig, McpConfig)
│        ├─ context/        # TokenCounter, ContextBudget
│        ├─ models/         # ModelClient ABC, OpenAI-compatible client, interfaces
│        ├─ runtime/        # AgentRuntime ABC, AgentSnapshot, EventBus, SessionStore, logging
│        └─ tools/          # ToolRegistry, ToolMeta, MCP bridge/contracts/stdio-provider
├─ apps/
│  └─ cli/                  # CLI adapter (Typer + Rich)
│     └─ src/
│        ├─ kcode_cli.py    # Entrypoint: app = Typer(...)
│        ├─ commands/        # chat, init, doctor, config
│        ├─ config/         # Multi-source config resolution
│        ├─ core/           # CliAgentRuntime — the agent loop
│        └─ tools/          # builtin_core, builtin_readonly
├─ tests/                   # Root-level test marker
├─ docs/                    # Documentation
├─ .github/                 # CI workflows
└─ pyproject.toml
```

### Core Invariant

`packages/core/` **never** imports from `apps/`. This is the key architectural boundary
that enables the desktop shell to reuse the same core without changes.

### Key Source Files

| File | Purpose |
|---|---|
| `apps/cli/src/kcode_cli.py` | Typer entrypoint, registers all commands |
| `apps/cli/src/commands/chat.py` | `run_chat()` — single-shot & interactive modes with streaming |
| `apps/cli/src/commands/init.py` | `run_init()` — creates `.kcode/` and `kcode.workspace.md` |
| `apps/cli/src/commands/doctor.py` | `run_doctor()` — health checks with colored output |
| `apps/cli/src/commands/config_cmd.py` | `config show` / `config validate` subcommands |
| `apps/cli/src/config/resolution.py` | `resolve_config()` — env -> user -> workspace -> CLI flags |
| `apps/cli/src/core/agent_runtime.py` | `CliAgentRuntime` — agent loop with `step()` + `step_stream()` |
| `apps/cli/src/tools/builtin_core.py` | Core tools: create_file, edit_file, search_code, run_command, git_*, todo_write/read |
| `apps/cli/src/tools/builtin_readonly.py` | Read-only tools: read_file, list_files |
| `packages/core/src/config/loader.py` | `AppConfig`, `ModelProviderConfig`, `ToolsConfig`, `load_config_from_dict()` |
| `packages/core/src/config/mcp.py` | `McpConfig`, `McpServerConfig` with transport/filtering/safety |
| `packages/core/src/context/tokens.py` | `TokenCounter` (tiktoken + char fallback), `ContextBudget` |
| `packages/core/src/models/interfaces.py` | `Message`, `ModelClient` ABC, `ModelResponse`, `StreamChunk`, `StreamAccumulator` |
| `packages/core/src/models/openai_compatible.py` | `OpenAICompatibleClient` — httpx-based OpenAI API client |
| `packages/core/src/runtime/contracts.py` | `AgentRuntime` ABC, `AgentSnapshot`, `AgentState` enum |
| `packages/core/src/runtime/events.py` | `EventBus`, `Event` |
| `packages/core/src/runtime/session.py` | `SessionStore`, `SessionRecord`, `MessageRecord`, `ToolRunRecord` |
| `packages/core/src/tools/contracts.py` | `ToolRegistry`, `ToolMeta`, `Tool`, `ToolOutput` |
| `packages/core/src/tools/mcp/bridge.py` | `register_mcp_tools()` — sync-async bridge |
| `packages/core/src/tools/mcp/contracts.py` | `McpToolProvider` ABC, MCP data models, safety heuristics |
| `packages/core/src/tools/mcp/stdio_provider.py` | `McpStdioProvider` — JSON-RPC stdio transport |

---

## Environment & Tooling

| Item | Value |
|---|---|
| Python | **3.13+** via conda env `expr` |
| Run command | `conda run -n expr python ...` |
| Shell | PowerShell on Windows |
| Build backend | `setuptools.build_meta` |
| Entry point | `kcode = apps.cli.src.kcode_cli:app` |
| Formatting | 2-space indent, CRLF line endings, UTF-8 encoding |
| Linting | `ruff check .` |
| Type checking | `mypy apps packages` |

### Unicode Note
PowerShell breaks Unicode when piped. **Write `.py` scripts to disk, then execute** —
do not pipe Unicode through PowerShell.

### Conda Retry
`conda run -n expr` occasionally fails on first try with "file in use" — just retry.

---

## Code Style

### General
- **Python 3.13+** — use modern syntax: `X | Y` unions, `list[T]`, `dict[K, V]`, `type` statement.
- **Pydantic v2** for all data models and config schemas.
- **Type hints everywhere** — all function signatures fully annotated.
- **`from __future__ import annotations`** at the top of every file.
- **2-space indentation** (per `.editorconfig`).
- **UTF-8** encoding, **CRLF** line endings.

### Naming
- `snake_case` for functions, methods, variables, modules.
- `PascalCase` for classes, exceptions, type aliases.
- `UPPER_SNAKE` for module-level constants.
- Private members prefixed with `_`.

### Docstrings
- Every public module gets a module-level docstring.
- Every public class and function gets a docstring (one-liner is fine).
- Use `"""triple double quotes"""`.

### Error Handling
- Raise specific exception types, never bare `Exception`.
- Tool errors return `ToolOutput(ok=False, message="...")` — they don't raise.
- Model/network errors are retried per `max_retries` config.

---

## Agent Runtime

### Execution Model

`CliAgentRuntime` is the central agent loop:

- **`step(user_input)`** — synchronous, returns `AgentSnapshot`
- **`step_stream(user_input)`** — streaming, yields `StreamChunk` objects then final `AgentSnapshot`

Both methods:
1. Append user message to history
2. Call model with tool specs
3. If model returns tool calls -> approve -> execute -> loop
4. If model returns text -> finish
5. If max_steps exceeded -> mark FAILED

### State Machine

`AgentState` enum: `IDLE -> THINKING -> TOOL_RUNNING -> AWAITING_APPROVAL -> FINISHED | FAILED`

### Approval Gate

Tools with `safety_class` in `("write", "system", "network")` require approval in interactive mode.
The approval handler supports two modes:
- **`ask`** (default): prompt user for each sensitive tool call
- **`auto`**: auto-approve all tool calls (for scripted/CI usage)

---

## Tool Safety Model

Every tool declares a `safety_class`:

| Class | Examples | Approval |
|-------|----------|----------|
| `read` | `read_file`, `list_files`, `search_code`, `git_status`, `git_diff` | No |
| `write` | `create_file`, `edit_file`, `git_commit` | Yes (interactive) |
| `system` | `run_command` | Yes (interactive) |
| `network` | (future: `web_fetch`) | Yes (interactive) |

### MCP Tool Safety
MCP tools derive safety from:
1. Explicit `x-kcode-safety-class` annotation in tool metadata
2. Name-based heuristics (`write/create/edit -> write`, `run/exec/shell -> system`, etc.)
3. Default to `read` if no signal

MCP tools get prefixed: `mcp__<server_name>__<tool_name>`

---

## Config Load Order

```
env vars -> user config (~/.config/kcode/config.yaml)
         -> workspace config (.kcode/config.yaml)
         -> CLI flags
```

Later sources override earlier ones. Secrets are never logged.

### Config Domains
- `provider` — provider name, base_url, api_key, models (with fallbacks)
- `model` — default model name, max_tokens, temperature, timeout, retries
- `tools` — command allowlist/blocklist, timeouts, file size limits
- `mcp` — server list with transport, filtering, safety overrides
- `workspace_root` — resolved workspace path
- `debug` — enable verbose logging

---

## Testing

### Run Tests
```powershell
conda run -n expr python -m pytest -v
```

### Test Paths
- `packages/core/tests/` — core unit tests
- `apps/cli/tests/` — CLI integration tests

### Conventions
- Test files: `test_*.py` in test directories.
- Each test directory has an `__init__.py` (empty).
- Use plain `assert` (pytest style), no `unittest.TestCase`.
- Test one behavior per test function.
- Name tests: `test_<what>_<condition>_<expected>`.
- Coverage target: **>=80%** for both `packages/core` and `apps/cli`.

### Test Patterns

**StubModel** — implement `ModelClient.complete()` with pre-built `Message` list:
```python
class StubModel:
    def complete(self, *, model, messages, tools):
        return ModelResponse(message=Message(role="assistant", content="..."))
```

**StubStreamingModel** — implement `complete_stream()` with pre-built chunk sequences:
```python
class StubStreamingModel:
    def complete_stream(self, *, model, messages, tools):
        yield StreamChunk(type=ChunkType.TEXT, delta="hello")
        yield StreamChunk(type=ChunkType.DONE)
```

**Monkeypatch `_now()`** in session tests — freeze `fixed_now = time.time()` first, then patch `_now` to return frozen values. Never use self-referencing lambdas.

---

## CLI Commands

| Command | Description |
|---|---|
| `kcode init` | Bootstrap `.kcode/` workspace |
| `kcode chat [message]` | Single-shot or interactive agent chat |
| `kcode config show` | Print resolved configuration |
| `kcode config validate` | Validate config sources |
| `kcode doctor` | Check runtime prerequisites |
| `kcode sessions list` | List past sessions |
| `kcode sessions resume <id>` | Resume a past session |
| `kcode --version` | Print version |
| `kcode --debug` | Enable debug logging |

### Chat Options
- `-w, --workspace <path>` — workspace directory (default: cwd)
- `-m, --model <name>` — model override
- `-p, --provider <name>` — provider override
- `-a, --approval <ask|auto>` — approval mode (default: ask)
- `--max-steps <N>` — max agent loop steps (default: 50)

---

## Development Workflow

### Setup
```powershell
conda activate expr
pip install -e ".[dev]"
```

### Before Committing
1. Run tests: `conda run -n expr python -m pytest -v`
2. Lint: `conda run -n expr ruff check .`
3. Type check: `conda run -n expr mypy apps packages`
4. Verify CLI: `kcode --version`

### Adding a New Tool
1. Create executor function in `apps/cli/src/tools/`.
2. Define `ToolMeta` with `name`, `description`, `safety_class`, `parameter_schema`.
3. Register via `ToolRegistry.register(Tool(meta=..., executor=...))`.
4. Add unit test in `apps/cli/tests/`.
5. If provider-agnostic, consider `packages/core/src/tools/`.

### Adding a New CLI Command
1. Create module in `apps/cli/src/commands/`.
2. Define function with Typer annotations.
3. Register in `apps/cli/src/kcode_cli.py` via `app.command()` or `app.add_typer()`.
4. Add test in `apps/cli/tests/`.

---

## Cross-Platform Notes

- **Paths**: Always use `pathlib.Path`, never string concatenation.
- **Shell commands**: Detect `platform.system()` — dispatch to PowerShell (Windows) or bash (Linux/macOS).
- **Line endings**: `.editorconfig` enforces CRLF; git handles normalization.
- **File encoding**: Always specify `encoding="utf-8"` when reading/writing text files.
- **Symlinks**: Be aware of Windows symlink permissions; use `resolve()` carefully.

---

## Build & Packaging

- Build backend: `setuptools.build_meta`
- Entry point: `kcode = "apps.cli.src.kcode_cli:app"`
- Packages discovered: `apps*`, `packages*`
- Install: `pip install -e .` (editable) or `pip install .` (standard)

### CI Matrix (`.github/workflows/ci.yml`)
- **quality**: ruff lint + mypy type check
- **test**: pytest on ubuntu, macos, windows
- **package**: install + verify `kcode --version` + `kcode doctor`

---

## E2E Validation Results

All four E2E scenarios passed:

| Test | Description | Steps | Result |
|------|-------------|-------|--------|
| Fibonacci | Create module + tests, run pytest | 4 | 6/6 tests passed |
| Todo App | Multi-file scaffolding (HTML/CSS/JS) | 4 | All files created correctly |
| Debug Fix | Read broken code, diagnose, fix | 2 | Bug fixed (off-by-one) |
| 2048 Game | Complex HTML/JS/CSS game | 3 | 12KB, full game with touch support |

---

## Desktop Extension Strategy (Phase 8)

Desktop should be a **thin shell** over the same core:

1. `packages/core/` provides all business logic via Python APIs
2. Desktop host wraps core + event bus -> WebSocket/IPC -> GUI
3. Options: PyWebView (Python-native), Tauri (Rust shell), Electron (JS shell)
4. Desktop inherits tools, sessions, policies, and runtime contracts unchanged

---

## Design Compass

KCode is CLI-first by design, but the architecture is intentionally desktop-ready.

### Architecture Principles
- **Hexagonal / Ports-and-Adapters** — `packages/core/` exposes pure ports; `apps/cli/` and later desktop are adapters.
- **Agent-Server Separation** — the same runtime can back CLI, desktop, and future remote surfaces.
- **Tool-First Capability Model** — every action is a typed tool with safety class, metadata, and auditability.
- **Streaming-First UX** — token and tool-call events are pushed as they happen, not batched after completion.
- **Session as Source of Truth** — sessions are durable, replayable, and inspectable.

### Modern Execution Patterns
- **Policy-as-Code** — approvals, permissions, and guardrails encoded in explicit rules, not implicit UI behavior.
- **Event Sourcing for Agent State** — conversations, tool runs, checkpoints, and decisions should be reconstructable.
- **Context Window Management** — count, compress, and retrieve context intentionally instead of stuffing blindly.
- **Observability-First** — structured logs, traces, run summaries, and cost metrics in the core loop.
- **Fail-Small Defaults** — untrusted actions are denied unless explicitly approved.
</INSTRUCTIONS>
