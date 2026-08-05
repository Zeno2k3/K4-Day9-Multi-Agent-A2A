"""JSONL trace writer.

README: "không append, chỉ cần lượt chạy mới nhất" — the file is truncated
at the start of every run (never appended across runs), then appended to
within that single run so a grader can replay the latest run's full
agent-by-agent handoff.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default(obj: Any) -> Any:
    return str(obj)


class TraceLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")
        self._seq = 0

    def _write(self, event: dict[str, Any]) -> None:
        self._seq += 1
        event.setdefault("ts", datetime.now(timezone.utc).isoformat())
        event.setdefault("step_seq", self._seq)
        self._fh.write(json.dumps(event, ensure_ascii=False, default=_default) + "\n")
        self._fh.flush()

    def run_start(self, **kwargs: Any) -> None:
        self._write({"event": "run_start", **kwargs})

    def run_end(self, **kwargs: Any) -> None:
        self._write({"event": "run_end", **kwargs})

    def case_start(self, case_id: str, **kwargs: Any) -> None:
        self._write({"event": "case_start", "case_id": case_id, **kwargs})

    def case_end(self, case_id: str, **kwargs: Any) -> None:
        self._write({"event": "case_end", "case_id": case_id, **kwargs})

    def case_failed(self, case_id: str, error: str, **kwargs: Any) -> None:
        self._write({"event": "case_failed", "case_id": case_id, "error": error, **kwargs})

    def agent_run(self, case_id: str, agent: str, **kwargs: Any) -> None:
        self._write({"event": "agent_run", "case_id": case_id, "agent": agent, **kwargs})

    def correction(
        self, case_id: str, agent: str, field: str, before: Any, after: Any, reason: str
    ) -> None:
        self._write(
            {
                "event": "correction",
                "case_id": case_id,
                "agent": agent,
                "field": field,
                "before": before,
                "after": after,
                "reason": reason,
            }
        )

    def close(self) -> None:
        self._fh.close()
