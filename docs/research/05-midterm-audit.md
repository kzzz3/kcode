# KCode Mid-Term Architecture Audit Report

**Date**: 2026-07-12
**Auditor**: KCode Agent (automated code review)
**Scope**: Full codebase — `packages/core/` + `apps/cli/`
**Test baseline**: 234 tests passing, mypy 0 errors, ruff clean

---

## 1. Executive Summary

KCode has completed **Phases 1–7** of the modern execution plan. The codebase demonstrates a well-structured hexagonal architecture with clean separation between the reusable core SDK (`packages/core/`) and the CLI adapter (`apps/cli/`). The streaming model, tool safety system, session persistence, and MCP adapter are all production-quality.

However, the audit reveals **10 actionable issues** — 2 high-severity, 4 medium, and 4 low — that should be addressed before the desktop extension phase. All issues are fixable within the existing architecture without structural changes.

---

## 2. Architecture Health Assessment

### 2.1 Core Boundary Integrity ✅

| Check | Result |
|-------|--------|
| `packages/core/` → `apps/` imports | **None detected** — boundary clean |
| Circular import chains | **None detected** — DAG structure confirmed |
| Pydantic v2 usage | **100%** — all config schemas use Pydantic v2 |
| Type annotation coverage | **Full** — all public APIs annotated |

### 2.2 Module Dependency Graph

```
apps/cli/src/
├── kcode_cli.py ──→ commands/
├── commands/chat.py ──→ core/agent_runtime.py ──→ packages/core/
├── commands/init.py ──→ (filesystem only)
├── commands/doctor.py ──→ (subprocess only)
├── commands/config.py ──→ config/resolution.py ──→ packages/core/config/
├── config/resolution.py ──→ packages/core/config/loader.py
├── core/agent_runtime.py ──→ packages/core/{runtime,models,tools}
├── tools/builtin_core.py ──→ packages/core/tools/contracts.py
└── tools/builtin_readonly.py ──→ packages/core/tools/contracts.py

packages/core/src/
├── config/ → (Pydantic models only, no cross-deps)
├── context/tokens.py → (self-contained, imports only models.interfaces)
├── models/ → (interfaces.py + openai_compatible.py)
├── runtime/ → (contracts, events, session, context, logging)
└── tools/ → (contracts + mcp/{bridge,contracts,stdio_provider})
```

**Assessment**: Dependency graph is clean and acyclic. The core SDK is genuinely UI-agnostic.

### 2.3 Design Pattern Compliance

| Pattern (from 04-modern-agent-patterns) | Status | Evidence |
|---|---|---|
| Agent-Server Separation | ✅ Full | `packages/core/` has zero CLI/UI deps |
| Tool-First Capability Model | ✅ Full | `ToolRegistry` + `ToolMeta.safety_class` |
| MCP Extension Layer | ✅ Full | `McpToolProvider` ABC + stdio transport |
| Streaming-First Interaction | ✅ Full | `step_stream()` + `StreamAccumulator` |
| Session Persistence | ✅ Full | SQLite/WAL with `SessionStore` |
| Context Window Management | ⚠ Partial | `TokenCounter` + `ContextBudget` exist but are **never used** in agent loop |
| Observability + Telemetry | ⚠ Partial | JSONL logging exists; no cost tracking or display |
| Policy-as-Code | ⚠ Partial | Approval gating exists; no deny rules or policy DSL |

---

## 3. Strengths

### 3.1 Streaming Architecture (Exemplary)

The `StreamChunk → StreamAccumulator → Message` pipeline (`packages/core/src/models/interfaces.py`) is elegant and well-designed:

- Clean `ChunkType` enum covers text, tool calls, usage, and done signals
- `StreamAccumulator.feed()` correctly handles partial tool-call argument accumulation
- The `step_stream()` method in `CliAgentRuntime` properly interleaves model output with tool execution
- This pattern matches or exceeds what Cursor and Claude Code offer

### 3.2 Tool Safety Model (Strong)

The 4-class safety model (`read`, `write`, `system`, `network`) with approval gating is well-implemented:

- Each `ToolMeta` declares its safety class
- `AgentLoopConfig.approval_required_classes` is configurable
- MCP tool safety uses 3-tier heuristic (annotation → name-based → default)
- The approval callback pattern is clean and testable

### 3.3 Session Store (Production-Quality)

SQLite/WAL session persistence with message and tool-run records:

- Proper foreign key relationships (session → messages → tool_runs)
- Session age-based reuse via `reuse_session_max_age_seconds`
- JSON serialization for complex fields (tool_calls, artifacts)
- Clean `SessionStore` API with create, append, get, list operations

### 3.4 MCP Adapter (Well-Abstracted)

The MCP tool provider is properly abstracted:

- `McpToolProvider` ABC defines the contract
- `McpStdioProvider` implements JSON-RPC over stdio
- `register_mcp_tools()` bridge handles sync↔async gap
- Config-driven server management via `McpConfig`

---

## 4. Weaknesses & Risks

### 4.1 HIGH — Duplicated Tool Execution Logic

**Files**: `apps/cli/src/core/agent_runtime.py`
**Lines**: `_execute_tool_calls()` (191–219) vs inline code in `step_stream()` (264–298)

Two nearly identical ~40-line blocks parse tool-call arguments, execute tools, handle errors, append messages, and record tool runs. This violates DRY and creates a maintenance risk — bug fixes in one path may not be applied to the other.

**Recommendation**: Extract a shared `_process_tool_call(tool_call)` method that both paths call. The method should:
1. Parse arguments (handle both string and dict)
2. Execute via `_run_tool()`
3. Append result message
4. Record tool run
5. Return the content string

**Cross-reference**: This pattern is consistent with the "Fail-Small Defaults" principle from the design compass — both paths handle errors, but diverge slightly in their error recording.

### 4.2 HIGH — ContextBudget Never Integrated

**Files**: `packages/core/src/context/tokens.py` (defined), `apps/cli/src/core/agent_runtime.py` (not used)

`ContextBudget` and `TokenCounter` are well-implemented but **never instantiated or used** in the agent loop. Long conversations will silently exceed model context windows, causing:
- API errors from providers that enforce limits
- Silent truncation by providers that don't
- Degraded output quality as context is lost

**Recommendation**: Integrate `ContextBudget` into `CliAgentRuntime.__init__()` and call `budget.update()` after each message append. Add a compaction strategy when `budget.utilization > 0.8`:
1. Count current tokens
2. If approaching limit, summarize older messages
3. Replace old messages with summary + recent context

**Cross-reference**: The comparative analysis (01) identifies "Context compaction, and summarization" as a candidate feature. The modern patterns doc (04) rates this as "⚠ Partial" and recommends Phase 8 integration.

### 4.3 MEDIUM — No Ignore Mechanism for File Tools

**Files**: `apps/cli/src/tools/builtin_core.py` (`_search_code`), `apps/cli/src/tools/builtin_readonly.py` (`_list_files`)

Both `search_code` and `list_files` use `Path.rglob()` without any ignore mechanism. This means:
- `.git/`, `node_modules/`, `__pycache__/`, `.venv/` are all traversed
- Performance degrades significantly on large repos
- Agent receives noise from irrelevant files

**Recommendation**: Implement a `.kcode/ignore` file (gitignore-style patterns) and integrate with `pathspec` library. Both tools should check against ignore patterns before processing files.

**Cross-reference**: Aider's repo-map uses intelligent file filtering. OpenCode uses `.gitignore`-aware traversal.

### 4.4 MEDIUM — `_resolve_within_root` Duplicated

**Files**: `apps/cli/src/tools/builtin_core.py:14-18`, `apps/cli/src/tools/builtin_readonly.py:13-17`

The identical function appears in both files. While small (5 lines), it's a code smell that will grow if more tool modules are added.

**Recommendation**: Extract to `apps/cli/src/tools/_utils.py` (or `packages/core/src/tools/path_utils.py` if it should be reusable by desktop).

### 4.5 MEDIUM — Missing Git Tools

**Current git tools**: `git_status`, `git_diff`, `git_commit`

**Missing**: `git_log` (commit history), `git_checkout` (branch switching)

These are essential for agent-driven debugging workflows. Without `git_log`, the agent cannot:
- Inspect recent changes to understand bug introduction points
- Verify commit history during code review
- Navigate branches for multi-branch work

**Recommendation**: Add `git_log` (with `--oneline`, `--since`, `--author` options) and `git_checkout` (with branch creation support).

### 4.6 MEDIUM — No Cost/Usage Display

**Files**: `apps/cli/src/commands/chat.py`

Token usage is emitted via events (`accumulator.usage`) but never displayed to the user or persisted. Users have no visibility into:
- Tokens consumed per turn
- Estimated cost per turn
- Cumulative session cost

**Recommendation**: After each turn in `_stream_to_terminal()`, display a compact usage line:
```
[dim]tokens: 1,234 in / 567 out | ~$0.03[/dim]
```

### 4.7 LOW — Synchronous Model Client

**File**: `packages/core/src/models/openai_compatible.py`

Uses `httpx.Client` (sync). Works fine for CLI but will block the event loop in async desktop environments.

**Recommendation**: Add `AsyncOpenAICompatibleClient` using `httpx.AsyncClient` when desktop work begins. The interface (`ModelClient` ABC) already supports both sync and async patterns.

### 4.8 LOW — `run_command` Uses shell=True

**File**: `apps/cli/src/tools/builtin_core.py:90`

`subprocess.run(command, shell=True)` has inherent shell injection risk. While the allowlist/blocklist mitigates this, `shell=False` with argument parsing would be safer.

**Recommendation**: For Phase 8, consider `shlex.split()` + `shell=False` for POSIX, or `subprocess.list2cmdline()` for Windows.

### 4.9 LOW — No Session Resume in REPL

**File**: `apps/cli/src/commands/chat.py:117-141`

The `_interactive_loop` creates a fresh runtime each time. If the user restarts `kcode chat`, they lose all context from previous sessions.

**Recommendation**: Add `--resume` flag that loads the most recent session from the store and replays messages.

### 4.10 LOW — Config Env Var Reading Missing

**File**: `apps/cli/src/config/resolution.py`

The config resolution comment says "env → file → CLI" but no actual environment variable reading is implemented. Users cannot set `KCODE_MODEL_API_KEY` or similar env vars.

**Recommendation**: Add env var reading with `KCODE_` prefix mapping in `resolve_config()`.

---

## 5. Risk Matrix

| # | Issue | Severity | Impact | Effort | Priority |
|---|-------|----------|--------|--------|----------|
| 4.1 | Duplicated tool execution | HIGH | Maintenance risk, divergent bugs | Low (1h) | **P0** |
| 4.2 | ContextBudget not integrated | HIGH | Silent context overflow on long sessions | Medium (3h) | **P0** |
| 4.3 | No ignore mechanism | MEDIUM | Performance, noise on large repos | Low (1.5h) | **P1** |
| 4.4 | `_resolve_within_root` duplicated | MEDIUM | Code smell, growth risk | Low (0.5h) | **P1** |
| 4.5 | Missing git tools | MEDIUM | Limited debugging capability | Low (1h) | **P1** |
| 4.6 | No cost display | MEDIUM | User visibility gap | Low (1h) | **P1** |
| 4.7 | Sync model client | LOW | Desktop readiness | Medium (2h) | **P2** |
| 4.8 | shell=True in run_command | LOW | Security surface | Medium (2h) | **P2** |
| 4.9 | No session resume | LOW | UX gap for long sessions | Low (1.5h) | **P2** |
| 4.10 | Config env vars missing | LOW | Config flexibility | Low (1h) | **P2** |

**Total estimated effort**: ~14.5 hours across all priorities.

---

## 6. Recommended Execution Order

### Immediate (P0) — Next 2 sessions
1. Extract shared tool utilities (`_resolve_within_root`)
2. Unify tool execution in `agent_runtime.py`
3. Integrate `ContextBudget` into agent loop with compaction strategy

### Short-term (P1) — Following 2 sessions
4. Add `.kcode/ignore` support
5. Add `git_log` + `git_checkout` tools
6. Add token/cost display in chat output

### Medium-term (P2) — Pre-desktop phase
7. Add `AsyncOpenAICompatibleClient`
8. Harden `run_command` shell safety
9. Add `--resume` flag to `kcode chat`
10. Add env var reading to config resolution

---

## 7. Competitor Alignment Check

| Capability | KCode (Current) | OpenCode | Aider | Cursor | Codex CLI |
|---|---|---|---|---|---|
| Context compaction | ❌ Missing | ✅ | ✅ | ✅ | ✅ |
| File ignore patterns | ❌ Missing | ✅ (.gitignore) | ✅ (.aiderignore) | ✅ | ✅ |
| Git log tool | ❌ Missing | ✅ | ✅ | ✅ | ✅ |
| Cost tracking | ❌ Missing | ✅ | ✅ | ✅ | ❌ |
| Session resume | ❌ Missing | ✅ | ✅ | ✅ | ✅ |
| Tool safety model | ✅ Strong | ⚠ | ❌ | ⚠ | ✅ |
| MCP support | ✅ Full | ✅ | ❌ | ✅ | ❌ |
| Streaming UX | ✅ Full | ✅ | ✅ | ✅ | ✅ |

KCode's core architecture is **competitive** with all major agents. The gaps are in **integration completeness** — the building blocks exist but aren't wired up. Closing these gaps is straightforward engineering work.

---

## 8. Conclusion

KCode is architecturally sound and production-ready for basic CLI coding workflows. The hexagonal architecture, streaming model, tool safety system, and MCP adapter are all high-quality implementations that match or exceed competitor patterns.

The primary risks are **integration gaps** rather than structural problems:
- `ContextBudget` exists but isn't used (context overflow risk)
- Tool execution is duplicated (maintenance risk)
- No file ignore mechanism (performance risk on large repos)

All identified issues are fixable within the existing architecture. The recommended execution order (P0 → P1 → P2) prioritizes correctness and safety over feature breadth, consistent with the project's "Precision over breadth" design pillar.

**Next action**: Begin P0 fixes — extract shared utilities, unify tool execution, and integrate context budget.