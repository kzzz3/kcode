# M1 Specification — "Make It Actually Useful"

## Goal

Transform KCode from a working prototype into a **productive daily-driver coding agent**
with streaming output, intelligent context management, a polished REPL, and external
tool extensibility via MCP.

## Design Principles (carried forward + new)

1. **Streaming-first** — all model output streams to the terminal in real-time.
2. **Context-aware** — automatic token counting, compaction before overflow.
3. **Extensible via MCP** — external tool servers are first-class citizens.
4. **Polished TUI** — Rich-powered REPL with syntax highlighting, tool status panels, diffs.
5. **Observability** — every model call, tool execution, and compaction is logged.

## Lessons from Industry Leaders

### From Claude Code / Codex CLI
- **Streaming with tool-call interleaving**: show partial text while tool calls are
  parsed in background. Don't block the UI on tool execution.
- **Approval flow inline**: display tool call + args, let user approve/deny in-stream.
- **Compact context strategy**: drop old tool outputs, keep summaries.

### From Aider
- **Repo map**: lightweight file tree + symbol index for context injection.
- **Lint/test after edit**: run configured linter/test after file mutations.
- **Structured edit format**: search/replace blocks, not free-form regex.

### From OpenCode (Go)
- **MCP as extension mechanism**: tools from external servers merge seamlessly.
- **Session replay**: persisted conversations are replayable.
- **Provider abstraction**: swap models without changing agent logic.

### From OpenHands
- **Agent-runtime separation**: core logic is UI-agnostic.
- **Event-driven architecture**: emit events, let UI subscribe.

---

## Deliverables

### D1: Streaming Model Responses
**Files changed**: `packages/core/src/models/interfaces.py`, `openai_compatible.py`,
`apps/cli/src/core/agent_runtime.py`

- Add `complete_stream()` to `ModelClient` ABC — yields `StreamChunk` objects.
- `StreamChunk` = `DeltaChunk(text)` | `ToolCallChunk(name, id, args_delta)` | `UsageChunk(tokens)`
- `OpenAICompatibleClient.complete_stream()` implements SSE parsing.
- `CliAgentRuntime` gains `step_stream()` that:
  - Prints text deltas to stdout in real-time via Rich Live.
  - Accumulates tool-call deltas, then executes when complete.
  - Falls back to non-streaming if provider doesn't support it.

### D2: Token Counting & Context Window Management
**Files changed**: `packages/core/src/context/` (new module)

- `TokenCounter` — counts tokens using `tiktoken` for OpenAI models, fallback to
  char-based estimation (4 chars ≈ 1 token).
- `ContextBudget` — tracks prompt + response token usage vs model limit.
- `ContextManager` — orchestrates:
  1. Pre-flight check before each model call.
  2. If over budget: compact old tool outputs → drop old messages → summarize.
  3. Injects system prompt with budget awareness.

### D3: Rich REPL UI
**Files changed**: `apps/cli/src/commands/chat.py`, new `apps/cli/src/ui/` module

- Rich-powered interactive REPL with:
  - Syntax-highlighted code blocks in responses.
  - Tool-call status panels (spinner while running, success/fail badge).
  - Approval prompts with tool args preview.
  - Markdown rendering for model output.
  - Status bar: model name, token usage, session ID.
- `prompt_toolkit` for input with history, multi-line (Ctrl+Enter), and
  auto-complete for slash commands.

### D4: MCP Adapter
**Files changed**: `packages/core/src/mcp/` (new module), config changes

- `McpServer` — connects to an MCP server via stdio or SSE transport.
- `McpToolAdapter` — wraps MCP tools into KCode's `Tool` contract.
- Config schema extension:
  ```yaml
  mcp:
    servers:
      - name: filesystem
        transport: stdio
        command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path"]
      - name: github
        transport: sse
        url: "http://localhost:3000"
  ```
- Tools from MCP servers merge into `ToolRegistry` with prefix: `mcp__<server>__<tool>`.
- Lifecycle: start servers on chat init, shut down on exit.

### D5: Message Compaction / Summarization
**Files changed**: `packages/core/src/context/compaction.py` (new)

- **Strategy 1 — Drop old tool outputs**: replace tool message content with
  `[compacted: {tool_name} produced {N} chars]`.
- **Strategy 2 — Summarize via model**: send old messages to model with
  "summarize this conversation so far" prompt, replace with summary message.
- Compaction triggers when `ContextBudget.remaining < threshold`.
- Always preserves: system prompt, last N user messages, all unsummarized tool calls.

### D6: Slash Commands in REPL
- `/help` — show available commands.
- `/model <name>` — switch model mid-session.
- `/compact` — force compaction.
- `/session` — show session info.
- `/clear` — clear screen.
- `/quit` — exit.

---

## Implementation Order

```
D1 (streaming) → D2 (token counting) → D5 (compaction) → D3 (rich REPL) → D4 (MCP) → D6 (slash commands)
```

Rationale:
- D1 is the highest-impact UX improvement.
- D2 and D5 are prerequisites for reliable long conversations.
- D3 builds on D1 (streaming into Rich panels).
- D4 is independent but benefits from D1's chunking infrastructure.
- D6 is a polish layer on D3.

## Testing Strategy

| Deliverable | Test Type | What to verify |
|---|---|---|
| D1 Streaming | Unit | StreamChunk parsing, fallback to non-streaming |
| D2 Tokens | Unit | TokenCounter accuracy, ContextBudget math |
| D3 REPL | Manual | Visual correctness, interaction flow |
| D4 MCP | Integration | Server lifecycle, tool registration, tool execution |
| D5 Compaction | Unit | Message reduction preserves essential context |
| D6 Slash | Unit | Command parsing, dispatch |

## Dependencies to Add

```
tiktoken>=0.7           # Token counting for OpenAI models
prompt_toolkit>=3.0     # Rich REPL input
mcp>=1.0                # MCP protocol client (if available on PyPI)
```

Fallback: if `tcp` / `mcp` package not available, implement minimal MCP JSON-RPC
over stdio manually (~200 lines).

## Non-Goals for M1
- Desktop GUI shell (M2).
- Remote sandbox execution.
- Multi-agent orchestration.
- Plugin marketplace.
