# KCode TUI Design

## Overview
KCode TUI is a terminal user interface built with Textual for the KCode coding agent.
It provides a modern, interactive chat interface with streaming support, tool visualization,
and session management.

## Architecture
The TUI is a thin shell over the existing `CliAgentRuntime`:
- Reuses `CliAgentRuntime` for agent loop (step/step_stream)
- Reuses `SessionStore` for session persistence
- Reuses `ToolRegistry` for tool management
- Uses `EventBus` for real-time updates

## Layout Design
```
?? Header (KCode logo + model name + status) ???????????????
?? Chat area (RichLog ? streaming messages + tool output) ??
?? Input area (multi-line TextArea) ????????????????????????
?? Status bar (state, tokens, cost, context utilization) ???
?? Footer (keyboard shortcuts) ?????????????????????????????
```

## Key Features
1. **Streaming chat**: Real-time token streaming with syntax highlighting
2. **Tool visualization**: Show tool calls with start/args/end status
3. **Approval gate**: Manual mode shows inline approval prompts
4. **Session management**: New session, resume, list sessions
5. **Model selection**: Display and switch models
6. **Keyboard shortcuts**: Ctrl+C exit, Ctrl+N new session, etc.

## File Structure
```
apps/cli/src/tui/
??? __init__.py
??? app.py                 # Main TUI application
??? widgets/
?   ??? __init__.py
?   ??? chat_area.py       # Chat message display
?   ??? input_area.py      # User input widget
?   ??? status_bar.py      # Status information
?   ??? approval_dialog.py # Tool approval dialog
?   ??? session_panel.py   # Session management
??? screens/
?   ??? __init__.py
?   ??? main_screen.py     # Main screen layout
??? utils/
    ??? __init__.py
    ??? message_formatter.py # Message formatting utilities
```
