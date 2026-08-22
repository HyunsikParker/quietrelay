from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from quietrelay.web import MAX_STATIC_BYTES, QuietRelayServer, safe_static_path


@contextmanager
def local_server(
    root: Path, plan_runner: Callable[[str], str] | None = None
) -> Iterator[tuple[QuietRelayServer, list[str]]]:
    calls: list[str] = []

    def runner(payload: str) -> str:
        calls.append(payload)
        if plan_runner is not None:
            return plan_runner(payload)
        return json.dumps({"external_actions": [], "plan": {"allocations": [], "reviews": []}})

    server = QuietRelayServer(("127.0.0.1", 0), root, runner, input_deadline=0.2, max_workers=3)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(
    server: QuietRelayServer, method: str, path: str, **kwargs: object
) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
    try:
        connection.request(method, path, **kwargs)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_safe_static_path_rejects_traversal(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")

    assert safe_static_path(tmp_path, "/") == (tmp_path / "index.html").resolve()
    assert safe_static_path(tmp_path, "/../secret") is None
    assert safe_static_path(tmp_path, "/%2e%2e/secret") is None
    assert safe_static_path(tmp_path, "/missing.js") is None


def test_health_and_plan_are_local_and_log_free(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    with local_server(tmp_path) as (server, calls):
        status, body = request(server, "GET", "/api/health")
        assert status == 200
        assert json.loads(body) == {"external_actions": [], "status": "ready"}

        port = server.server_address[1]
        status, body = request(
            server,
            "POST",
            "/api/plan",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
            },
        )
        assert status == 200
        assert json.loads(body)["external_actions"] == []
        assert calls == ["{}"]


def test_plan_rejects_cross_origin_before_runner(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    with local_server(tmp_path) as (server, calls):
        status, body = request(
            server,
            "POST",
            "/api/plan",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://example.com",
            },
        )
        assert status == 403
        assert json.loads(body) == {"error": "local_origin_required"}
        assert calls == []


def test_health_rejects_nonlocal_host(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    with local_server(tmp_path) as (server, calls):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            connection.putrequest("GET", "/api/health", skip_host=True)
            connection.putheader("Host", "example.com")
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == 403
            assert json.loads(response.read()) == {"error": "local_host_required"}
        finally:
            connection.close()
        assert calls == []


def test_partial_body_expires_without_invoking_runner(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    with local_server(tmp_path) as (server, calls):
        started = time.monotonic()
        client = socket.create_connection(server.server_address, timeout=1)
        try:
            client.sendall(
                b"POST /api/plan HTTP/1.1\r\n"
                + f"Host: 127.0.0.1:{server.server_address[1]}\r\n".encode()
                + b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{"
            )
            client.settimeout(1)
            try:
                client.recv(1024)
            except (TimeoutError, ConnectionResetError):
                pass
        finally:
            client.close()
        assert time.monotonic() - started < 1
        assert calls == []
        assert request(server, "GET", "/api/health")[0] == 200


def test_static_assets_are_size_bounded(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    oversized = tmp_path / "large.js"
    oversized.write_bytes(b"x" * (MAX_STATIC_BYTES + 1))
    with local_server(tmp_path) as (server, _calls):
        status, body = request(server, "GET", "/large.js")
        assert status == 413
        assert json.loads(body) == {"error": "asset_too_large"}


def test_health_remains_available_and_second_plan_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    started = threading.Event()
    release = threading.Event()

    def slow_runner(_payload: str) -> str:
        started.set()
        assert release.wait(timeout=2)
        return json.dumps({"external_actions": [], "plan": {"allocations": [], "reviews": []}})

    with local_server(tmp_path, slow_runner) as (server, calls):
        port = server.server_address[1]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
        }
        first_result: list[tuple[int, bytes]] = []
        first = threading.Thread(
            target=lambda: first_result.append(
                request(server, "POST", "/api/plan", body=b"{}", headers=headers)
            )
        )
        first.start()
        assert started.wait(timeout=1)
        assert request(server, "GET", "/api/health")[0] == 200
        second_status, second_body = request(
            server, "POST", "/api/plan", body=b"{}", headers=headers
        )
        assert second_status == 429
        assert json.loads(second_body) == {"error": "local_agent_busy"}
        release.set()
        first.join(timeout=2)
        assert first_result[0][0] == 200
        assert calls == ["{}"]
