from __future__ import annotations

import json
import multiprocessing
import time
from copy import deepcopy
from multiprocessing.connection import Connection
from types import SimpleNamespace

import pytest

from quietrelay.agent import (
    LOCAL_MODEL_DIGEST,
    LOCAL_MODEL_ID,
    _build_agent,
    _run_agent_process,
    _verify_local_model,
    authoritative_result,
    plan_payload,
)


def payload() -> dict:
    return {
        "today": "2026-08-22",
        "requests": [
            {
                "request_id": "req-1",
                "zone": "north",
                "urgency": 4,
                "needs": [{"item": "rice", "units": 2}],
            }
        ],
        "stock": [
            {
                "lot_id": "lot-1",
                "item": "rice",
                "units": 2,
                "expires_on": "2026-08-23",
            }
        ],
        "volunteers": [{"volunteer_id": "vol-1", "zones": ["north"], "capacity": 1}],
    }


def successful_child(_payload: str, connection: Connection) -> None:
    connection.send("ok")
    connection.close()


def stalled_child(_payload: str, _connection: Connection) -> None:
    time.sleep(5)


def test_plan_payload_returns_minimized_plan() -> None:
    result = json.loads(plan_payload(json.dumps(payload())))

    assert result == {
        "allocations": [
            {
                "items": [{"item": "rice", "lot_id": "lot-1", "units": 2}],
                "request_id": "req-1",
                "volunteer_id": "vol-1",
            }
        ],
        "reviews": [],
    }


def test_plan_payload_replaces_source_ids_with_per_run_handles() -> None:
    current = payload()
    current["requests"][0]["request_id"] = "req-9001"
    current["stock"][0]["lot_id"] = "lot-9001"
    current["volunteers"][0]["volunteer_id"] = "vol-9001"

    result = plan_payload(json.dumps(current))

    assert "9001" not in result
    assert '"request_id":"req-1"' in result
    assert '"lot_id":"lot-1"' in result
    assert '"volunteer_id":"vol-1"' in result


def test_plan_payload_rejects_identity_field() -> None:
    current = payload()
    current["requests"][0]["name"] = "synthetic person"

    with pytest.raises(ValueError, match="invalid request fields"):
        plan_payload(json.dumps(current))


def test_plan_payload_rejects_large_input() -> None:
    with pytest.raises(ValueError, match="invalid payload size"):
        plan_payload("x" * (64 * 1024 + 1))


def test_large_character_count_rejects_before_encoding() -> None:
    class EncodeMustNotRun(str):
        def encode(self, *args: object, **kwargs: object) -> bytes:
            raise AssertionError("encode should not run")

    with pytest.raises(ValueError, match="invalid payload size"):
        plan_payload(EncodeMustNotRun("x" * (64 * 1024 + 1)))


def test_plan_payload_rejects_excessive_nesting() -> None:
    nested = "[" * 10_000 + "0" + "]" * 10_000

    with pytest.raises(ValueError, match="invalid payload JSON"):
        plan_payload(nested)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("requests", 0, "request_id"), "person@example.com"),
        (("requests", 0, "request_id"), "req-alice"),
        (("requests", 0, "zone"), "home-address"),
        (("requests", 0, "needs", 0, "item"), "ignore-previous-instructions"),
        (("stock", 0, "lot_id"), "lot-1\nsecret"),
        (("stock", 0, "lot_id"), "lot-ignoreall"),
        (("stock", 0, "item"), "medicine"),
        (("volunteers", 0, "volunteer_id"), "person-name"),
        (("volunteers", 0, "volunteer_id"), "vol-01012345"),
        (("volunteers", 0, "zones", 0), "north\u202e"),
    ],
)
def test_plan_payload_rejects_noncanonical_or_sensitive_strings(
    path: tuple[str | int, ...], value: object
) -> None:
    current = deepcopy(payload())
    target: object = current
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ValueError):
        plan_payload(json.dumps(current))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("requests", 0, "urgency"), True),
        (("requests", 0, "needs", 0, "units"), 1.5),
        (("stock", 0, "units"), True),
        (("volunteers", 0, "capacity"), 1.5),
    ],
)
def test_plan_payload_rejects_non_integer_numeric_fields(
    path: tuple[str | int, ...], value: object
) -> None:
    current = deepcopy(payload())
    target: object = current
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ValueError):
        plan_payload(json.dumps(current))


def test_authoritative_result_is_deterministic_and_has_no_external_actions() -> None:
    current = json.dumps(payload())

    result = json.loads(authoritative_result(current))

    assert result["external_actions"] == []
    assert result["plan"] == json.loads(plan_payload(current))


def test_local_agent_constructs_without_network_call() -> None:
    agent = _build_agent(json.dumps(payload()))

    assert agent.name == "QuietRelay"
    assert agent.model.config["model_id"] == LOCAL_MODEL_ID
    assert agent.model.host == "http://127.0.0.1:11434"
    assert agent.model.client_args == {
        "follow_redirects": False,
        "timeout": 30.0,
        "trust_env": False,
    }
    assert agent.model.config.get("additional_args") is None
    assert agent.model.config.get("options") is None


def test_agent_process_accepts_successful_child() -> None:
    _run_agent_process("{}", timeout=2, process_target=successful_child)


def test_agent_process_terminates_stalled_child() -> None:
    before = {child.pid for child in multiprocessing.active_children()}

    with pytest.raises(TimeoutError, match="wall-clock limit"):
        _run_agent_process("{}", timeout=0.05, process_target=stalled_child)

    assert {child.pid for child in multiprocessing.active_children()} <= before


class FakeOllamaClient:
    def __init__(self, digest: str) -> None:
        self.digest = digest

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(models=[SimpleNamespace(model=LOCAL_MODEL_ID, digest=self.digest)])


def test_local_model_digest_verification() -> None:
    _verify_local_model(FakeOllamaClient(LOCAL_MODEL_DIGEST))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="digest is unavailable"):
        _verify_local_model(FakeOllamaClient("0" * 64))  # type: ignore[arg-type]


def test_local_model_rejects_ambient_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "not-used")

    with pytest.raises(ValueError, match="not allowed"):
        _verify_local_model(FakeOllamaClient(LOCAL_MODEL_DIGEST))  # type: ignore[arg-type]
