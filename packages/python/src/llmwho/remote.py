"""Bounded, fail-open delivery to a self-hosted LLMWho Collector."""

import json
from queue import Empty, Full, Queue
from threading import Lock, Thread
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .collector import OTLP_EVENT_ATTRIBUTE, OTLP_EVENT_TYPE
from .observation import validate_observation
from .version import __version__


_STOP = object()


def _collector_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("collector_url must be an HTTP(S) URL without credentials or query")
    return value.rstrip("/")


def otlp_logs_payload(events: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for event in events:
        records.append(
            {
                "body": {
                    "stringValue": json.dumps(
                        event,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                },
                "attributes": [
                    {
                        "key": OTLP_EVENT_ATTRIBUTE,
                        "value": {"stringValue": OTLP_EVENT_TYPE},
                    },
                    {
                        "key": "llmwho.schema.version",
                        "value": {"stringValue": event["schema_version"]},
                    },
                ],
            }
        )
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "llmwho-sdk"},
                        }
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "llmwho-python", "version": __version__},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


class RemoteStore:
    """Queue observations without adding Collector latency to host requests."""

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        protocol: str = "native",
        max_queue: int = 1024,
        batch_size: int = 50,
        flush_interval: float = 0.05,
        request_timeout: float = 2.0,
    ) -> None:
        if protocol not in {"native", "otlp"}:
            raise ValueError("protocol must be native or otlp")
        if max_queue < 1 or batch_size < 1:
            raise ValueError("max_queue and batch_size must be positive")
        if flush_interval < 0 or request_timeout <= 0:
            raise ValueError("invalid remote store timing")
        self.url = _collector_base_url(url)
        self.protocol = protocol
        self.max_queue = max_queue
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.request_timeout = request_timeout
        self._token = token
        self._queue: Queue[object] = Queue(maxsize=max_queue)
        self._state_lock = Lock()
        self._closed = False
        self.dropped = 0
        self.delivery_failures = 0
        self.delivered = 0
        self._worker = Thread(
            target=self._run,
            name="llmwho-collector-sink",
            daemon=True,
        )
        self._worker.start()

    @property
    def endpoint(self) -> str:
        path = "/v1/logs" if self.protocol == "otlp" else "/api/v1/observations"
        return f"{self.url}{path}"

    def append(self, event: dict[str, Any]) -> bool:
        validate_observation(event)
        with self._state_lock:
            if self._closed:
                self.dropped += 1
                return False
            try:
                self._queue.put_nowait(event)
            except Full:
                self.dropped += 1
                return False
        return True

    def _payload(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if self.protocol == "otlp":
            return otlp_logs_payload(events)
        return {"observations": events}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"llmwho-python/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _send(self, events: list[dict[str, Any]]) -> None:
        body = json.dumps(
            self._payload(events),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        with urlopen(request, timeout=self.request_timeout) as response:
            response.read()

    def _deliver(self, events: list[dict[str, Any]]) -> None:
        try:
            self._send(events)
        except Exception:
            self.delivery_failures += len(events)
        else:
            self.delivered += len(events)

    def _run(self) -> None:
        stopping = False
        while not stopping:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                break
            batch = [item]
            deadline = monotonic() + self.flush_interval
            while len(batch) < self.batch_size:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                try:
                    next_item = self._queue.get(timeout=remaining)
                except Empty:
                    break
                if next_item is _STOP:
                    self._queue.task_done()
                    stopping = True
                    break
                batch.append(next_item)
            self._deliver(batch)
            for _ in batch:
                self._queue.task_done()

    def read(self, limit: int | None = None) -> list[dict[str, Any]]:
        suffix = "" if limit is None else f"?limit={max(0, int(limit))}"
        request = Request(
            f"{self.url}/api/events{suffix}",
            headers=self._headers(),
            method="GET",
        )
        with urlopen(request, timeout=self.request_timeout) as response:
            value = json.load(response)
        if not isinstance(value, list):
            raise ValueError("Collector events response must be an array")
        for event in value:
            validate_observation(event)
        return value

    def close(self, timeout: float = 2.0) -> bool:
        deadline = monotonic() + max(0, timeout)
        with self._state_lock:
            if self._closed:
                return not self._worker.is_alive()
            self._closed = True
        try:
            self._queue.put(_STOP, timeout=max(0, deadline - monotonic()))
        except Full:
            return False
        self._worker.join(timeout=max(0, deadline - monotonic()))
        return not self._worker.is_alive()

    def __enter__(self) -> "RemoteStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
