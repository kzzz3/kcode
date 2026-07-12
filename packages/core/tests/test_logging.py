from __future__ import annotations

import json
from pathlib import Path

from packages.core.src.runtime.logging import log_event


def test_log_event_creates_jsonl(tmp_path: Path) -> None:
    log_event("unit.test", {"k": 1}, workspace_root=tmp_path)

    path = tmp_path / ".kcode" / "logs" / "runtime.jsonl"
    assert path.exists()

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 1
    assert records[0]["event"] == "unit.test"
    assert records[0]["payload"]["k"] == 1
