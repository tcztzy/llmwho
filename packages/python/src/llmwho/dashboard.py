"""Dependency-free loopback dashboard server."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from .storage import JSONLStore
from .summary import summarize


HTML_PATH = Path(__file__).with_name("dashboard.html")


class ReadableStore(Protocol):
    def read(self, limit: int | None = None) -> list[dict]: ...


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadableStore,
        handler_class: type[BaseHTTPRequestHandler] | None = None,
    ) -> None:
        self.store = store
        super().__init__(address, handler_class or DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: object) -> None:
        self._send(
            status,
            "application/json; charset=utf-8",
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", HTML_PATH.read_bytes())
                return
            if parsed.path == "/favicon.ico":
                self._send(204, "image/x-icon", b"")
                return
            if parsed.path == "/api/summary":
                self._json(200, summarize(self.server.store.read()))
                return
            if parsed.path == "/api/events":
                raw_limit = parse_qs(parsed.query).get("limit", ["500"])[0]
                try:
                    limit = min(2000, max(1, int(raw_limit)))
                except ValueError:
                    limit = 500
                self._json(200, self.server.store.read(limit=limit))
                return
        except Exception:
            self._json(500, {"error": "unable to read local observation store"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        return


def create_dashboard_server(
    *,
    storage_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 7734,
    store: ReadableStore | None = None,
) -> DashboardServer:
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    return DashboardServer((host, port), store or JSONLStore(storage_path))


def serve_dashboard(
    *,
    storage_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 7734,
) -> None:
    server = create_dashboard_server(storage_path=storage_path, host=host, port=port)
    print(f"LLMWho dashboard: http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
