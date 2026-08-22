"""Loopback-only HTTP surface for the integrated QuietRelay demo."""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path, PurePosixPath
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import unquote, urlsplit

from .agent import MAX_PAYLOAD_BYTES, run_local_plan

LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_STATIC_BYTES = 4 * 1024 * 1024
STATIC_CHUNK_BYTES = 64 * 1024
INPUT_DEADLINE_SECONDS = 5.0
OUTPUT_TIMEOUT_SECONDS = 65.0
MAX_REQUEST_WORKERS = 8
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def safe_static_path(root: Path, request_path: str) -> Path | None:
    parsed = urlsplit(request_path)
    try:
        decoded = unquote(parsed.path, errors="strict")
    except UnicodeDecodeError:
        return None
    if "\x00" in decoded or "\\" in decoded:
        return None
    relative = "index.html" if decoded == "/" else decoded.removeprefix("/")
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
        return None
    return candidate


class QuietRelayServer(ThreadingMixIn, HTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_REQUEST_WORKERS

    def __init__(
        self,
        address: tuple[str, int],
        static_root: Path,
        plan_runner: Callable[[str], str] = run_local_plan,
        *,
        input_deadline: float = INPUT_DEADLINE_SECONDS,
        max_workers: int = MAX_REQUEST_WORKERS,
    ) -> None:
        if input_deadline <= 0 or not 1 <= max_workers <= MAX_REQUEST_WORKERS:
            raise ValueError("invalid server limits")
        self.static_root = static_root.resolve()
        self.plan_runner = plan_runner
        self.input_deadline = input_deadline
        self.plan_lock = threading.Lock()
        self.worker_slots = threading.BoundedSemaphore(max_workers)
        super().__init__(address, QuietRelayHandler, bind_and_activate=True)

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not self.worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.worker_slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.worker_slots.release()

    def handle_error(self, _request: socket.socket, _client_address: Any) -> None:
        """Expected malformed local clients must not emit tracebacks or paths."""


class QuietRelayHandler(BaseHTTPRequestHandler):
    server: QuietRelayServer
    server_version = "QuietRelay"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self._input_timer: threading.Timer | None = threading.Timer(
            self.server.input_deadline, self._expire_input
        )
        self._input_timer.daemon = True
        self._input_timer.start()

    def finish(self) -> None:
        self._finish_input_phase()
        try:
            super().finish()
        except (TimeoutError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _expire_input(self) -> None:
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.connection.close()
        except OSError:
            pass

    def _finish_input_phase(self) -> None:
        timer = getattr(self, "_input_timer", None)
        if timer is not None:
            timer.cancel()
            self._input_timer = None
        try:
            self.connection.settimeout(OUTPUT_TIMEOUT_SECONDS)
        except OSError:
            pass

    def log_message(self, _format: str, *args: object) -> None:
        """Do not persist request paths, headers, or payload-derived values."""

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (TimeoutError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _send_file(self, target: Path, content_type: str) -> None:
        size = target.stat().st_size
        if not 0 <= size <= MAX_STATIC_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "asset_too_large"})
            return
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with target.open("rb") as handle:
                for block in iter(lambda: handle.read(STATIC_CHUNK_BYTES), b""):
                    self.wfile.write(block)
        except (TimeoutError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _host_is_local(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "").lower() in {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
        }

    def _origin_is_local(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        port = self.server.server_address[1]
        return origin.lower() in {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._finish_input_phase()
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def do_GET(self) -> None:  # noqa: N802
        self._finish_input_phase()
        if not self._host_is_local():
            self._json(HTTPStatus.FORBIDDEN, {"error": "local_host_required"})
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/api/health" and not parsed.query:
            self._json(
                HTTPStatus.OK,
                {"external_actions": [], "status": "ready"},
            )
            return
        if parsed.path.startswith("/api/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        target = safe_static_path(self.server.static_root, self.path)
        if target is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send_file(target, content_type)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path != "/api/plan" or parsed.query:
            self._finish_input_phase()
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._host_is_local() or not self._origin_is_local():
            self._finish_input_phase()
            self._json(HTTPStatus.FORBIDDEN, {"error": "local_origin_required"})
            return
        if self.headers.get("Transfer-Encoding") is not None:
            self._finish_input_phase()
            self._json(HTTPStatus.BAD_REQUEST, {"error": "content_length_required"})
            return
        if self.headers.get_content_type() != "application/json":
            self._finish_input_phase()
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "json_required"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        raw_length = lengths[0] if len(lengths) == 1 else ""
        if (
            not raw_length.isascii()
            or not raw_length.isdigit()
            or len(raw_length) > len(str(MAX_PAYLOAD_BYTES))
        ):
            self._finish_input_phase()
            self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "content_length_required"})
            return
        length = int(raw_length)
        if not 0 < length <= MAX_PAYLOAD_BYTES:
            self._finish_input_phase()
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "payload_too_large"})
            return
        try:
            body = self.rfile.read(length)
        except (TimeoutError, ConnectionResetError, OSError):
            self._finish_input_phase()
            return
        self._finish_input_phase()
        if len(body) != length:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "incomplete_request"})
            return
        if not self.server.plan_lock.acquire(blocking=False):
            self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "local_agent_busy"})
            return
        try:
            payload = body.decode("utf-8", errors="strict")
            result = self.server.plan_runner(payload)
            parsed_result = json.loads(result)
            if (
                not isinstance(parsed_result, dict)
                or set(parsed_result) != {"external_actions", "plan"}
                or parsed_result["external_actions"] != []
            ):
                raise ValueError("invalid authoritative result")
            encoded = json.dumps(parsed_result, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
            if len(encoded) > MAX_RESPONSE_BYTES:
                raise ValueError("authoritative result is too large")
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return
        except (RuntimeError, TimeoutError, OSError):
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "local_agent_unavailable"})
            return
        finally:
            self.server.plan_lock.release()
        self._send(HTTPStatus.OK, encoded, "application/json; charset=utf-8")


def serve(static_root: Path, *, port: int = DEFAULT_PORT) -> None:
    if not 1 <= port <= 65_535:
        raise ValueError("invalid local port")
    if static_root.is_symlink():
        raise ValueError("frontend build is unavailable")
    root = static_root.resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        raise ValueError("frontend build is unavailable")
    server = QuietRelayServer((LOCAL_HOST, port), root)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
