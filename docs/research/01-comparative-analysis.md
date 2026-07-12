# Comparative Analysis: Lessons from OpenCode/Crush, Aider, and OpenHands

## 1. OpenCode / Crush

**Evidence source**: `https://raw.githubusercontent.com/opencode-ai/opencode/main/README.md`, `https://raw.githubusercontent.com/charmbracelet/crush/main/README.md`

### What we can adopt
- Strong terminal-native experience with session management and structured configuration files.
- MCP integration as a first-class extensibility mechanism.
- LSP integration for developer-context enrichment.
- Persistent session/conversation storage.
- Clear separation between providers, tools, configuration, and UI.

### Risks to avoid
- OpenCode README marks itself as early development and later archived, which suggests we must prioritize stable interfaces and testable boundaries.
- Crush README emphasizes provider auto-update and metrics; KCode should make both explicit and optional.

## 2. Aider

**Evidence source**: `https://raw.githubusercontent.com/Aider-AI/aider/main/README.md`

### What we can adopt
- Repository map / codebase indexing concept for larger monorepos.
- Git-aware workflows with high-quality commit messages and reviewable diffs.
- Lint/test integration after code mutations.
- Rich multimodal and web-page support in product narrative, but we should implement only what can remain robust.

### Risks to avoid
- Copy/paste and repo-map features are valuable, but they need bounded memory and latency budgets.
- Commit automation should be opt-in and reviewable, not implicit magic.

## 3. OpenHands

**Evidence source**: `https://raw.githubusercontent.com/All-Hands-AI/OpenHands/main/README.md`

### What we can adopt
- Agent-server separation: backend/runtime can be local now and remote/sandboxed later.
- Multi-backend thinking: local machine, docker sandbox, VM, or managed runtime.
- Automations and workflow orchestration as a future extension layer.
- Use of an agent-client protocol mindset for future plug-in agents.

### Risks to avoid
- OpenHands is large and web/control-center oriented. KCode should remain terminal-first and minimal.
- We should avoid copying the full OpenHands architecture before validating the core coding loop.

## 4. Design Synthesis

### Product pillars
1. **Precision over breadth** - excellent single-repo coding agent first.
2. **Safe by default** - commands, file mutations, and network use are observable and controllable.
3. **Layered extensibility** - tools, models, storage, and UI are replaceable.
4. **Testable from day one** - pure core with isolated IO/runtime adapters.

### Candidate feature stack
- Typed config loader with JSON schema validation.
- Multi-provider LLM abstraction.
- Streaming agent loop with tool calling.
- Core tool registry: `read_file`, `edit_file`, `create_file`, `run_command`, `git_*`, `search_code`, `web_fetch`.
- Session state, context compaction, and summarization.
- Local-first persistence (SQLite).
- Non-interactive and interactive CLI modes.

### Industrial-grade quality bar
- Unit tests for core loop and tool contracts.
- Integration tests for CLI commands.
- Reproducible install, build, and run scripts.
- Structured logging and crash-safe diagnostics.
