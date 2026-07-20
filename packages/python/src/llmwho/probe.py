"""Explicit, judge-free active probe suite for OpenAI-compatible chat APIs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import socket
from time import perf_counter
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

from .observation import new_observation
from .storage import NDJSONStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _chat_url(base_url: str) -> str:
    if not base_url or not isinstance(base_url, str):
        raise ValueError("base_url is required")
    clean = base_url.rstrip("/")
    path = urlsplit(clean).path.rstrip("/").lower()
    if path.endswith("/chat/completions"):
        return clean
    if path.endswith("/v1"):
        return f"{clean}/chat/completions"
    return f"{clean}/v1/chat/completions"


def _content(payload: Any) -> Optional[str]:
    try:
        value = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _exact(expected: str) -> Callable[[Optional[str]], bool]:
    return lambda value: isinstance(value, str) and value.strip() == expected


def _json_contract(value: Optional[str]) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return json.loads(value) == {"llmwho": 1}
    except json.JSONDecodeError:
        return False


SMOKE_CASES = (
    {
        "id": "exact_instruction",
        "check": "exact:LLMWHO_OK",
        "prompt": "Reply with exactly LLMWHO_OK and no other characters.",
        "score": _exact("LLMWHO_OK"),
    },
    {
        "id": "json_contract",
        "check": 'json:{"llmwho":1}',
        "prompt": 'Return exactly one JSON object: {"llmwho":1}. Do not use Markdown.',
        "score": _json_contract,
    },
    {
        "id": "invalid_premise",
        "check": "exact:FALSE",
        "prompt": "Is the statement 2 + 2 = 5 true? Reply with exactly FALSE.",
        "score": _exact("FALSE"),
    },
    {
        "id": "arithmetic",
        "check": "exact:323",
        "prompt": "Compute 17 multiplied by 19. Reply with digits only.",
        "score": _exact("323"),
    },
)


def _request_redactions(url: str, api_key: Optional[str]) -> int:
    count = 1 if api_key else 0
    count += sum(
        1
        for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if key.lower()
        in {"api_key", "apikey", "key", "token", "access_token", "signature", "sig"}
    )
    return count


def _identity_rollup(events: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    candidates: dict[str, int] = {}
    for event in events:
        identity = event["identity"]
        statuses[identity["status"]] = statuses.get(identity["status"], 0) + 1
        observed = identity.get("observed_model")
        if observed:
            candidates[observed] = candidates.get(observed, 0) + 1
    return {
        "statuses": dict(sorted(statuses.items())),
        "observed_models": dict(sorted(candidates.items())),
    }


def probe(
    *,
    base_url: str,
    model: str,
    api_key: Optional[str] = None,
    suite: str = "smoke",
    storage_path: Optional[str] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send the explicit smoke suite and return a content-free report."""

    if suite != "smoke":
        raise ValueError("only the smoke suite is available in LLMWho 0.1")
    if not model or not isinstance(model, str):
        raise ValueError("model is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    url = _chat_url(base_url)
    store = NDJSONStore(storage_path)
    started_at = _utc_now()
    cases = []
    events = []
    for case in SMOKE_CASES:
        body = json.dumps(
            {
                "model": model,
                "temperature": 0,
                "max_tokens": 32,
                "messages": [
                    {
                        "role": "system",
                        "content": "This is a deterministic API compatibility test. Follow the exact-output instruction.",
                    },
                    {"role": "user", "content": case["prompt"]},
                ],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "llmwho/0.1"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        started = perf_counter()
        status_code = None
        outcome = "network_error"
        response_payload = None
        response_headers: dict[str, str] = {}
        output_size = 0
        try:
            with urlopen(Request(url, data=body, headers=headers, method="POST"), timeout=timeout) as response:
                status_code = response.status
                raw = response.read()
                output_size = len(raw)
                response_headers = dict(response.headers.items())
                try:
                    parsed = json.loads(raw)
                    response_payload = parsed if isinstance(parsed, dict) else None
                except (UnicodeDecodeError, json.JSONDecodeError):
                    response_payload = None
                outcome = "success" if 200 <= status_code < 400 else "http_error"
        except HTTPError as error:
            status_code = error.code
            outcome = "http_error"
            response_headers = dict(error.headers.items()) if error.headers else {}
        except (TimeoutError, socket.timeout):
            outcome = "timeout"
        except URLError as error:
            outcome = "timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "network_error"
        except Exception as error:
            outcome = "timeout" if "timeout" in type(error).__name__.lower() else "network_error"
        duration_ms = (perf_counter() - started) * 1000
        answer = _content(response_payload)
        passed = outcome == "success" and bool(case["score"](answer))
        declared = response_payload.get("model") if response_payload and isinstance(response_payload.get("model"), str) else None
        response_meta: dict[str, Any] = {"output_bytes": output_size}
        if status_code is not None:
            response_meta["status_code"] = status_code
        if declared:
            response_meta["declared_model"] = declared
        if response_payload and isinstance(response_payload.get("system_fingerprint"), str):
            response_meta["system_fingerprint"] = response_payload["system_fingerprint"]
        event = new_observation(
            url=url,
            duration_ms=duration_ms,
            outcome=outcome,
            source="probe",
            claimed_model=model,
            declared_model=declared,
            response_headers=response_headers,
            request={
                "operation": "chat.completions",
                "claimed_model": model,
                "stream": False,
                "input_bytes": len(body),
                "role_count": 2,
                "probe_case_id": case["id"],
            },
            response=response_meta,
            probe={
                "case_id": case["id"],
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "check": case["check"],
            },
            redactions=_request_redactions(url, api_key),
        )
        events.append(event)
        try:
            store.append(event)
        except Exception:
            pass
        cases.append(
            {
                "case_id": case["id"],
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "outcome": outcome,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "identity": event["identity"],
            }
        )
    score = sum(case["score"] for case in cases) / len(cases)
    endpoint = events[0]["endpoint"] if events else new_observation(
        url=url, duration_ms=0, outcome="network_error"
    )["endpoint"]
    return {
        "schema_version": "1",
        "suite": "smoke",
        "model": model,
        "endpoint": endpoint,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "completed": True,
        "capability": {
            "passed": sum(1 for case in cases if case["passed"]),
            "total": len(cases),
            "mean_score": score,
        },
        "identity": _identity_rollup(events),
        "cases": cases,
    }
