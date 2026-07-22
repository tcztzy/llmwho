"""Versioned JSONL worker used by the Node science runtime."""

from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
import json
import sys
from typing import Any, TextIO

from .registry import PROTOCOL_VERSION, PluginRegistry


class _Discard:
    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None


def _write(stream: TextIO, response: Mapping[str, Any]) -> None:
    stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def _error(request_id: Any, code: str) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "id": request_id,
        "error": {"code": code, "message": "science request failed"},
    }


def serve(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    discard = _Discard()
    with redirect_stdout(discard), redirect_stderr(discard):
        registry = PluginRegistry()
    for line in input_stream:
        request_id: Any = None
        try:
            request = json.loads(line)
            if not isinstance(request, Mapping):
                raise TypeError
            request_id = request.get("id")
            if request.get("protocol_version") != PROTOCOL_VERSION:
                _write(output_stream, _error(request_id, "protocol_mismatch"))
                continue
            method = request.get("method")
            params = request.get("params", {})
            if method == "ping":
                result: Any = {"protocol_version": PROTOCOL_VERSION}
            elif method == "plugins":
                result = registry.descriptors()
            elif method == "analyze":
                if not isinstance(params, Mapping):
                    raise TypeError
                with redirect_stdout(discard), redirect_stderr(discard):
                    result = registry.run(params.get("plugin"), params.get("payload"))
            elif method == "shutdown":
                _write(
                    output_stream,
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "id": request_id,
                        "result": {"shutdown": True},
                    },
                )
                return 0
            else:
                _write(output_stream, _error(request_id, "unknown_method"))
                continue
            _write(
                output_stream,
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "id": request_id,
                    "result": result,
                },
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            _write(output_stream, _error(request_id, "invalid_request"))
        except Exception:
            _write(output_stream, _error(request_id, "plugin_failure"))
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
