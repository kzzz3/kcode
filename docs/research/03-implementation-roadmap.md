# Implementation Roadmap

## Phase 1 - Repository Bootstrap
- Init git repository and baseline structure.
- Add top-level docs, config schema draft, and initial README.
- Add editorconfig/lint/test scaffolding.
- Deliverable: reproducible project skeleton with docs and empty test harness.

## Phase 2 - Core CLI and Config
- Implement typed configuration loader and validator.
- Implement CLI entrypoints: `kcode init`, `kcode config show`, `kcode doctor`.
- Add structured logger and debug toggle.
- Deliverable: CLI can load config, validate environment, and exit cleanly.

## Phase 3 - Model Abstraction
- Define provider-agnostic message/tool-call interface.
- Implement OpenAI-compatible adapter first.
- Add token counting hooks and retry policy.
- Deliverable: non-interactive prompt roundtrip against configured provider.

## Phase 4 - Agent Loop and Core Tools
- Implement observe-think-act loop.
- Add read/search/list file tools.
- Add command runner with approval mode and timeout.
- Deliverable: agent can inspect repo and answer code questions using tools.

## Phase 5 - Editable Workflow
- Add create/edit file tools with diff output.
- Add git status/diff/commit tools.
- Add redaction and audit logging.
- Deliverable: agent can patch files and generate reviewable git changes.

## Phase 6 - Session Persistence
- Add SQLite session store.
- Add context compaction/summarization.
- Add replay and export command.
- Deliverable: reproducible agent sessions with restart capability.

## Phase 7 - Extensibility and Packaging
- Define MCP/tool adapter interface.
- Add docs, example config, and installer.
- Add integration tests and CI plan.
- Deliverable: release candidate with documented extension points.

## Evidence Standard
Each phase must include:
1. runnable CLI command
2. automated tests
3. updated docs
4. changelog entry
