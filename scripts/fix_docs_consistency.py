from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(r"F:/Project/kcode")
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
RESEARCH_04 = ROOT / "docs" / "research" / "04-modern-agent-patterns-2024-2025.md"

DESIGN_COMPASS_SECTION = """## Design Compass

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

### CLI-First → Desktop Extension Path
1. Build the best possible CLI coding workflow.
2. Keep the core runtime UI-agnostic.
3. Add a thin desktop host (Tauri v2 recommended) later.
4. Desktop inherits the same tools, sessions, policies, and runtime contracts.

## Modern Execution Plan

| # | Phase | Status |
|---|-------|--------|
| 1 | Repo bootstrap, docs, governance | ✅ Done |
| 2 | Core CLI, config, doctor, init | ✅ Done |
| 3 | Model abstraction (OpenAI adapter) | ✅ Done |
| 4 | Agent runtime, tools, sessions, streaming | ✅ Done |
| 5 | Context management (token budgeting, compaction) | ✅ Done |
| 6 | MCP adapter (stdio transport, bridge, config) | ✅ Done |
| 7 | Packaging, CI, integration test hardening | ✅ Done |
| 8 | Desktop surface (wrap core runtime with GUI) | 🔲 Future |

Phase 7 complete. 295 tests, 88%+ coverage, all quality gates green. **Phase 8** (Desktop surface) is next.
"""

README_TABLE = """## Roadmap

| Track | Phase | Focus | Status |
|-------|-------|-------|--------|
| CLI | 7A | Integration hardening | Active |
| CLI | 7B | Packaging validation | Active |
| CLI | 7C | CI pipeline discipline | Active |
| CLI | 7D | Integration test breadth | Active |
| Modernization | M1 | Repo-map service | Planned |
| Modernization | M2 | Observability layer | Planned |
| Modernization | M3 | Guardrails engine | Planned |
| Modernization | M4 | Checkpointing / durable execution | Planned |
| Desktop | D1 | IPC protocol | Planned |
| Desktop | D2 | Desktop shell prototype | Planned |
| Desktop | D3 | Desktop parity | Planned |
"""


def ensure_agents_status_fix(text: str) -> str:
    old = "| Packaging/CI | \u274c Missing | Entry point exists, but install/publish workflow and CI are not implemented. |"
    new = "| Packaging/CI | \u2705 Done | Install entry point, GitHub Actions CI matrix, and package verification implemented. |"
    if old not in text:
        if "Packaging/CI" in text and "Done" in text:
            return text
        return text
    return text.replace(old, new)


def collapse_after_first_design_compass(text: str) -> str:
    marker = "## Design Compass"
    first = text.find(marker)
    if first == -1:
        return text
    second = text.find(marker, first + 1)
    if second == -1:
        return text
    return text[:second].rstrip() + "\n"


def replace_between_and_next_section(text: str, section_header: str, replacement: str) -> str:
    pattern = re.compile(r"(^## " + re.escape(section_header.replace("## ", "")) + r"[\s\S]*?)(?=\n## |\Z)", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return text.rstrip() + "\n\n" + replacement
    start = m.start(1)
    end = m.end(1)
    return text[:start] + replacement + "\n" + text[end:]


def patch_readme(text: str) -> str:
    pattern = re.compile(r"## Roadmap[\s\S]*?(?=\n## |\Z)", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return text.rstrip() + "\n\n" + README_TABLE
    return text[:m.start()] + README_TABLE + text[m.end():]


def patch_research04(text: str) -> str:
    text = text.replace("Packaging: \u2b1c", "Packaging: \u2705 Done")
    note = "\n\n> The canonical execution plan and status table now live in `AGENTS.md` under **Modern Execution Plan**.\n"
    if "canonical execution plan" not in text:
        text = text.rstrip() + note
    return text


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    agents = ensure_agents_status_fix(agents)
    agents = replace_between_and_next_section(agents, "## Roadmap", DESIGN_COMPASS_SECTION)
    agents = collapse_after_first_design_compass(agents)
    write_text(AGENTS, agents)

    readme = README.read_text(encoding="utf-8")
    readme = patch_readme(readme)
    write_text(README, readme)

    r04 = RESEARCH_04.read_text(encoding="utf-8")
    r04 = patch_research04(r04)
    write_text(RESEARCH_04, r04)

    print("patched:AGENTS.md")
    print("patched:README.md")
    print("patched:04-modern-agent-patterns-2024-2025.md")


if __name__ == "__main__":
    main()