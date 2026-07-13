"""Help modal for TUI -- comprehensive keyboard shortcuts and command reference."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Markdown


HELP_MD = """\
## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New session |
| `Ctrl+L` | Clear chat display |
| `Ctrl+B` | Toggle sidebar |
| `Ctrl+K` | Command palette |
| `Ctrl+H` | Show this help |
| `Ctrl+Q` | Quit |
| `Escape` | Cancel streaming / close dialog |

## Slash Commands

Type `/` in the empty input to open the command palette.

### Session
| Command | Alias | Description |
|---------|-------|-------------|
| `/new` | — | Start a fresh chat session |
| `/compact` | — | Compact conversation to save tokens |
| `/clear` | — | Clear the current chat display |
| `/sessions` | — | List and switch between sessions |
| `/refresh` | — | Reload sessions list |
| `/init` | — | Create / update kcode.workspace.md |

### View
| Command | Alias | Description |
|---------|-------|-------------|
| `/sidebar` | `/sb` | Show / hide the sidebar panel |
| `/theme` | `/t` | Switch between available themes |

### Model
| Command | Alias | Description |
|---------|-------|-------------|
| `/model` | `/m` | Change the active LLM model |

### Config
| Command | Alias | Description |
|---------|-------|-------------|
| `/approval` | `/ap` | Toggle ask / auto approval mode |

### Help & App
| Command | Alias | Description |
|---------|-------|-------------|
| `/help` | `/h` | Show this help screen |
| `/doctor` | `/dr` | Check runtime health status |
| `/quit` | `/q` | Exit KCode TUI |

## Input

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | Insert newline |
| `/` (empty input) | Open slash command palette |
| `↑` `↓` | Navigate command palette |
| `Tab` / `Enter` | Confirm palette selection |
| `Escape` | Cancel streaming / close palette |

---
*Press Escape to close*
"""


class HelpScreen(ModalScreen[None]):
  """Modal help screen showing keyboard shortcuts and commands."""

  DEFAULT_CSS = """
  HelpScreen {
    align: center top;
    background: $boost 60%;
  }

  #help-box {
    width: 72;
    max-width: 86;
    height: auto;
    max-height: 85%;
    border: thick $accent;
    background: $surface;
    padding: 0;
    overflow-y: auto;
  }

  #help-content {
    padding: 1 2;
    height: auto;
  }

  #help-content > Markdown {
    height: auto;
  }
  """

  def compose(self) -> ComposeResult:
    with Vertical(id="help-box"):
      with VerticalScroll(id="help-content"):
        yield Markdown(HELP_MD)

  def on_key(self, event) -> None:
    if event.key == "escape":
      self.dismiss(None)
