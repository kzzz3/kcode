"""Structured diagnostics and logging hooks."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def log_event(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    workspace_root: Path | None = None,
) -> None:
    """Append a structured log line.

    If *workspace_root* is provided the log is written under
    ``<workspace_root>/.kcode/logs/runtime.jsonl``; otherwise it falls back
    to ``.kcode/logs/runtime.jsonl`` relative to the current working directory.
    """
    base = workspace_root if workspace_root is not None else Path(".")
    log_path = base / ".kcode" / "logs" / "runtime.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), "event": name, "payload": payload or {}}
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")