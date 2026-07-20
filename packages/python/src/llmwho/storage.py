"""Append-only NDJSON event storage."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Optional, Union

from .observation import validate_observation


class NDJSONStore:
    def __init__(self, path: Optional[Union[os.PathLike[str], str]] = None) -> None:
        self.path = Path(path or Path.home() / ".llmwho" / "events.ndjson")
        self._lock = Lock()

    def append(self, event: dict[str, Any]) -> None:
        validate_observation(event)
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, line.encode("utf-8"))
            finally:
                os.close(descriptor)

    def read(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    event = json.loads(line)
                    validate_observation(event)
                    events.append(event)
        return events[-limit:] if limit is not None else events

    def iter_events(self) -> Iterable[dict[str, Any]]:
        yield from self.read()
