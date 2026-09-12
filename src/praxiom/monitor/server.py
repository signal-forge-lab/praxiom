"""Passive device monitor plus bounded local Human Teaching channel."""
from __future__ import annotations

import argparse
import ipaddress
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

from praxiom.knowledge.teaching import HumanTeachingStore
from praxiom.monitor.projection import LatestFrameStore, MonitorSnapshotBuilder

__all__ = ["create_server", "main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17680
_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/monitor.css": ("monitor.css", "text/css; charset=utf-8"),
    "/monitor.js": ("monitor.js", "text/javascript; charset=utf-8"),
    "/praxiom-icon.png": ("praxiom-icon.png", "image/png"),
}


def _loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _MonitorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, *, builder, frame_store, human_store) -> None:
        super().__init__(address, handler)
        self.builder = builder
        self.frame_store = frame_store
        self.human_store = human_store


class _Handler(BaseHTTPRequestHandler):
    server: _MonitorServer
    server_version = "PraxiomMonitor/0.1"
    sys_version = ""

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _send(self, status: int, content_type: str, data: bytes, *, body: bool = True) -> None:
        self._headers(status, content_type, len(data))
        if body:
            self.wfile.write(data)

    def _get(self, *, body: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/snapshot":
            data = json.dumps(
                self.server.builder.build(), separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", data, body=body)
            return
        if path == "/healthz":
            data = b'{"ok":true,"name":"praxiom-monitor","mode":"passive-device+human-channel"}\n'
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", data, body=body)
            return
        if path == "/api/frame":
            frame = self.server.frame_store.read_frame()
            if frame is None:
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"frame unavailable\n", body=body)
            else:
                self._send(HTTPStatus.OK, "image/png", frame, body=body)
            return
        if path == "/api/human-channel":
            data = json.dumps(
                self.server.human_store.snapshot(recent=50),
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", data, body=body)
            return
        static = _STATIC.get(path)
        if static is not None:
            name, content_type = static
            data = files("praxiom.monitor.static").joinpath(name).read_bytes()
            self._send(HTTPStatus.OK, content_type, data, body=body)
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n", body=body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._get(body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._get(body=False)

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("content-length-invalid") from exc
        if length < 1 or length > 32_768:
            raise ValueError("request-body-size-invalid")
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("json-object-required")
        return value

    def _send_json(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", data)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = self.path.split("?", 1)[0]
        # Device projection may be explicitly exposed on LAN for observation,
        # but Human Teaching is a durable knowledge-write boundary.  Keep that
        # boundary loopback-only unless a future authenticated channel is
        # designed explicitly; --allow-lan must never widen write authority as
        # a side effect of widening monitor visibility.
        client_host = str(self.client_address[0]) if self.client_address else ""
        if not _loopback(client_host):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "human-channel-write-loopback-only"},
            )
            return
        try:
            payload = self._read_json_body()
            if path == "/api/human-teaching":
                item = self.server.human_store.submit(
                    payload.get("text", ""),
                    teaching_kind=payload.get("teaching_kind", "other"),
                    source="operator",
                    context=payload.get("context"),
                )
                self._send_json(
                    HTTPStatus.CREATED, {"ok": True, "teaching_id": item.teaching_id}
                )
                return
            if path == "/api/human-question":
                item = self.server.human_store.ask(
                    payload.get("prompt", ""), context=payload.get("context")
                )
                self._send_json(
                    HTTPStatus.CREATED, {"ok": True, "question_id": item.question_id}
                )
                return
            if path == "/api/human-answer":
                item = self.server.human_store.answer(
                    payload.get("question_id", ""),
                    payload.get("text", ""),
                    teaching_kind=payload.get("teaching_kind", "other"),
                    context=payload.get("context"),
                )
                self._send_json(
                    HTTPStatus.CREATED, {"ok": True, "teaching_id": item.teaching_id}
                )
                return
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD, POST")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed

    def log_message(self, format: str, *args: Any) -> None:
        return None


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    state_root: Path | str | None = None,
    allow_lan: bool = False,
) -> ThreadingHTTPServer:
    if not _loopback(host) and not allow_lan:
        raise ValueError("non-loopback monitor bind requires allow_lan=True")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 to 65535")
    store = LatestFrameStore(state_root)
    builder = MonitorSnapshotBuilder(state_root=state_root, frame_store=store)
    human_store = HumanTeachingStore(state_root)
    return _MonitorServer(
        (host, port), _Handler, builder=builder, frame_store=store, human_store=human_store
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Praxiom read-only passive monitor")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--allow-lan", action="store_true")
    args = parser.parse_args()
    server = create_server(
        args.host,
        args.port,
        state_root=args.state_root,
        allow_lan=args.allow_lan,
    )
    print(f"Praxiom Monitor: http://{args.host}:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
