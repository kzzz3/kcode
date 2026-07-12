import pathlib

p = pathlib.Path(r"apps/cli/src/tui/screens/main_screen.py")
text = p.read_text(encoding="utf-8").replace("\r\n", "\n")

old = "    self._refresh_sessions()\n    self._load_custom_commands()"
new = "    self._refresh_sessions()\n    self._load_custom_commands()\n    # Show welcome banner in chat area\n    chat = self.query_one(ChatArea)\n    chat.show_welcome()"

text = text.replace(old, new)
p.write_text(text.replace("\n", "\r\n"), encoding="utf-8")
print("main_screen.py updated: welcome banner wired")