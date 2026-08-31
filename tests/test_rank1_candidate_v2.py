from __future__ import annotations

import json
import multiprocessing
import random
import time
from multiprocessing.connection import Connection
from typing import Any

import pytest

import quietrelay.rank1_candidate_v2 as candidate_v2
from quietrelay.agent import LOCAL_INVOCATION_LIMITS, authoritative_result
from quietrelay.rank1_candidate_v2 import (
    RecoverySessionV2,
    _canonical_records,
    _exercise_rank1_v2_agent,
    _run_rank1_v2_process,
    _stock_aware_incremental_plan,
    authoritative_plan_v2,
    run_rank1_evidence_v2,
    run_rank1_plan_v2,
)

EXPECTED_STEPS = ["inspect_conflicts", "select_recovery", "validate_recovery"]


def _successful_process(_payload: str, connection: Connection) -> None:
    connection.send({"selected_option": "baseline", "steps": EXPECTED_STEPS})
    connection.close()


def _error_process(_payload: str, connection: Connection) -> None:
    connection.send("error")
    connection.close()


def _stalled_process(_payload: str, _connection: Connection) -> None:
    time.sleep(5)


def _payload(
    *,
    requests: list[dict[str, Any]] | None = None,
    stock: list[dict[str, Any]] | None = None,
    volunteers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "today": "2026-08-22",
        "requests": requests or [],
        "stock": stock or [],
        "volunteers": volunteers or [],
    }


def _request(
    request_id: str,
    zone: str,
    urgency: int,
    *needs: tuple[str, int],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "zone": zone,
        "urgency": urgency,
        "needs": [{"item": item, "units": units} for item, units in needs],
    }


def _stock(lot_id: str, item: str, units: int, expires_on: str = "2026-08-23") -> dict:
    return {
        "lot_id": lot_id,
        "item": item,
        "units": units,
        "expires_on": expires_on,
    }


def _volunteer(volunteer_id: str, zones: list[str], capacity: int = 1) -> dict:
    return {"volunteer_id": volunteer_id, "zones": zones, "capacity": capacity}


def _v2_plan(payload: dict[str, Any]) -> dict[str, Any]:
    records = _canonical_records(json.dumps(payload))
    return json.loads(
        json.dumps(
            {
                "allocations": [
                    {
                        "request_id": row.request_id,
                        "volunteer_id": row.volunteer_id,
                        "items": [
                            {"lot_id": item.lot_id, "item": item.item, "units": item.units}
                            for item in row.items
                        ],
                    }
                    for row in _stock_aware_incremental_plan(records).allocations
                ],
                "reviews": [
                    {
                        "request_id": row.request_id,
                        "reason": row.reason,
                        "evidence": list(row.evidence),
                    }
                    for row in _stock_aware_incremental_plan(records).reviews
                ],
            }
        )
    )


def _options(session: RecoverySessionV2) -> dict[str, dict[str, Any]]:
    return {
        row["option_id"]: row
        for row in json.loads(session.inspect())["options"]
    }


def test_grok_stock_shortage_counterexample_keeps_oats_request() -> None:
    payload = _payload(
        requests=[
            _request("req-9001", "north", 5, ("rice", 1)),
            _request("req-9002", "north", 4, ("oats", 1)),
        ],
        stock=[_stock("lot-9001", "oats", 1)],
        volunteers=[_volunteer("vol-9001", ["north"])],
    )

    v2 = _v2_plan(payload)
    control = json.loads(authoritative_result(json.dumps(payload)))["plan"]

    assert [row["request_id"] for row in v2["allocations"]] == ["req-2"]
    assert v2["allocations"][0]["items"][0]["item"] == "oats"
    assert len(v2["allocations"]) >= len(control["allocations"])
    assert len(v2["reviews"]) <= len(control["reviews"])


def test_incremental_path_reassigns_slots_and_supports_capacity_above_one() -> None:
    payload = _payload(
        requests=[
            _request("req-1", "north", 5, ("rice", 1)),
            _request("req-2", "south", 4, ("oats", 1)),
            _request("req-3", "south", 3, ("milk", 1)),
        ],
        stock=[
            _stock("lot-1", "rice", 1),
            _stock("lot-2", "oats", 1),
            _stock("lot-3", "milk", 1),
        ],
        volunteers=[
            _volunteer("vol-1", ["north", "south"], capacity=2),
            _volunteer("vol-2", ["north"]),
        ],
    )

    plan = _v2_plan(payload)

    assert len(plan["allocations"]) == 3
    assert {row["volunteer_id"] for row in plan["allocations"]} == {"vol-1", "vol-2"}
    assert sum(row["volunteer_id"] == "vol-1" for row in plan["allocations"]) == 2


def test_exact_fefo_handles_multi_need_expiry_and_lot_ties() -> None:
    payload = _payload(
        requests=[_request("req-1", "east", 5, ("rice", 3), ("oats", 1))],
        stock=[
            _stock("lot-1", "rice", 99, "2026-08-21"),
            _stock("lot-2", "rice", 1, "2026-08-23"),
            _stock("lot-3", "rice", 2, "2026-08-23"),
            _stock("lot-4", "oats", 1, "2026-08-22"),
        ],
        volunteers=[_volunteer("vol-1", ["east"])],
    )

    items = _v2_plan(payload)["allocations"][0]["items"]

    assert items == [
        {"item": "rice", "lot_id": "lot-2", "units": 1},
        {"item": "rice", "lot_id": "lot-3", "units": 2},
        {"item": "oats", "lot_id": "lot-4", "units": 1},
    ]


def test_stock_is_committed_only_after_request_enters_matching() -> None:
    payload = _payload(
        requests=[
            _request("req-1", "north", 5, ("rice", 1)),
            _request("req-2", "south", 4, ("rice", 1)),
        ],
        stock=[_stock("lot-1", "rice", 1)],
        volunteers=[_volunteer("vol-1", ["south"])],
    )

    plan = _v2_plan(payload)

    assert [row["request_id"] for row in plan["allocations"]] == ["req-2"]
    assert plan["reviews"][0]["reason"] == "volunteer_capacity"


def test_empty_queue_returns_exact_existing_schema_and_deterministic_tie() -> None:
    payload = json.dumps(_payload())
    session = RecoverySessionV2(payload)
    options = _options(session)

    assert options["baseline"] == {
        "allocated_requests": 0,
        "option_id": "baseline",
        "unresolved_decisions": 0,
    }
    assert options["stock_aware_incremental"]["allocated_requests"] == 0
    session.select("baseline")
    assert json.loads(session.validate())["selected_option"] == "baseline"

    result = json.loads(authoritative_plan_v2(payload))
    assert set(result) == {"external_actions", "plan"}
    assert result == {"external_actions": [], "plan": {"allocations": [], "reviews": []}}


@pytest.mark.parametrize(
    "payload, message",
    [
        ("{", "invalid payload JSON"),
        (
            json.dumps(
                _payload(
                    requests=[
                        _request("req-1", "north", 5, ("rice", 1)),
                        _request("req-1", "south", 4, ("oats", 1)),
                    ]
                )
            ),
            "duplicate request id",
        ),
        (
            json.dumps(
                _payload(stock=[_stock("lot-1", "rice", 1), _stock("lot-1", "oats", 1)])
            ),
            "duplicate lot id",
        ),
        (
            json.dumps(
                _payload(
                    volunteers=[
                        _volunteer("vol-1", ["north"]),
                        _volunteer("vol-1", ["south"]),
                    ]
                )
            ),
            "duplicate volunteer id",
        ),
    ],
)
def test_malformed_and_duplicate_identifiers_fail_closed(payload: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RecoverySessionV2(payload)


def test_three_stage_order_is_causal_one_shot_and_data_minimized() -> None:
    raw = _payload(
        requests=[_request("req-9001", "north", 5, ("rice", 1))],
        stock=[_stock("lot-9001", "rice", 1)],
        volunteers=[_volunteer("vol-9001", ["north"])],
    )
    payload = json.dumps(raw)
    session = RecoverySessionV2(payload)

    with pytest.raises(ValueError, match="prior inspection"):
        session.select("baseline")
    with pytest.raises(ValueError, match="allowlisted selection"):
        session.validate()

    inspection = session.inspect()
    assert "9001" not in inspection
    with pytest.raises(ValueError, match="first and one-shot"):
        session.inspect()
    with pytest.raises(ValueError, match="not allowlisted"):
        session.select("invented")

    selection = session.select("baseline")
    assert "9001" not in selection
    with pytest.raises(ValueError, match="prior inspection"):
        session.select("baseline")

    validation = session.validate()
    receipt = json.loads(validation)
    assert "9001" not in validation
    assert receipt["external_actions"] == []
    assert [row["step"] for row in receipt["audit"]["steps"]] == [
        "inspect_conflicts",
        "select_recovery",
        "validate_recovery",
    ]
    with pytest.raises(ValueError, match="allowlisted selection"):
        session.validate()

    result = json.loads(session.authoritative_result())
    assert set(result) == {"external_actions", "plan"}
    assert result["external_actions"] == []
    assert "9001" not in json.dumps(result)


def test_run_path_uses_fixed_limits_and_ignores_model_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        _payload(
            requests=[
                _request("req-1", "north", 5, ("rice", 1)),
                _request("req-2", "south", 4, ("oats", 1)),
            ],
            stock=[_stock("lot-1", "rice", 1), _stock("lot-2", "oats", 1)],
            volunteers=[
                _volunteer("vol-1", ["north", "south"]),
                _volunteer("vol-2", ["north"]),
            ],
        )
    )
    observed: dict[str, Any] = {}

    def fake_process(current_payload: str) -> dict[str, Any]:
        observed["payload"] = current_payload
        return {"selected_option": "stock_aware_incremental", "steps": EXPECTED_STEPS}

    monkeypatch.setattr(candidate_v2, "_run_rank1_v2_process", fake_process)

    evidence = json.loads(run_rank1_evidence_v2(payload))
    result = json.loads(run_rank1_plan_v2(payload))

    assert observed["payload"] == payload
    assert set(evidence) == {
        "audit",
        "external_actions",
        "metrics",
        "plan",
        "selected_option",
    }
    assert evidence["selected_option"] == "stock_aware_incremental"
    assert [row["step"] for row in evidence["audit"]["steps"]] == EXPECTED_STEPS
    assert evidence["metrics"]["constraint_violations"] == 0
    assert set(result) == {"external_actions", "plan"}
    assert result["external_actions"] == []
    assert len(result["plan"]["allocations"]) == 2
    assert "invented" not in json.dumps(result)


def test_child_returns_only_sanitized_selection_and_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        _payload(
            requests=[_request("req-9001", "north", 5, ("rice", 1))],
            stock=[_stock("lot-9001", "rice", 1)],
            volunteers=[_volunteer("vol-9001", ["north"])],
        )
    )
    sent: list[object] = []
    observed: dict[str, Any] = {}

    class CaptureConnection:
        def send(self, value: object) -> None:
            sent.append(value)

        def close(self) -> None:
            observed["closed"] = True

    class FakeAgent:
        def __init__(self, session: RecoverySessionV2) -> None:
            self.session = session

        def __call__(self, prompt: str, *, limits: dict[str, int]) -> str:
            observed["prompt"] = prompt
            observed["limits"] = limits
            self.session.inspect()
            self.session.select("baseline")
            self.session.validate()
            return "invented model prose with a fake delivery"

    monkeypatch.setattr(candidate_v2, "_verify_local_model", lambda: None)
    monkeypatch.setattr(candidate_v2, "_build_rank1_agent_v2", FakeAgent)

    _exercise_rank1_v2_agent(payload, CaptureConnection())  # type: ignore[arg-type]

    assert sent == [{"selected_option": "baseline", "steps": EXPECTED_STEPS}]
    assert observed["limits"] == LOCAL_INVOCATION_LIMITS
    assert "synthetic queue" in observed["prompt"]
    assert observed["closed"] is True
    assert "9001" not in json.dumps(sent)
    assert "invented" not in json.dumps(sent)


def test_isolated_process_accepts_only_sanitized_receipt() -> None:
    assert _run_rank1_v2_process("{}", timeout=2, process_target=_successful_process) == {
        "selected_option": "baseline",
        "steps": EXPECTED_STEPS,
    }

    with pytest.raises(RuntimeError, match="exercise failed"):
        _run_rank1_v2_process("{}", timeout=2, process_target=_error_process)


def test_isolated_process_terminates_on_hard_timeout() -> None:
    before = {child.pid for child in multiprocessing.active_children()}

    with pytest.raises(TimeoutError, match="wall-clock limit"):
        _run_rank1_v2_process("{}", timeout=0.05, process_target=_stalled_process)

    assert {child.pid for child in multiprocessing.active_children()} <= before


@pytest.mark.parametrize(
    ("child_receipt", "message"),
    [
        (
            {"selected_option": "stock_aware_incremental", "steps": EXPECTED_STEPS},
            "selection policy",
        ),
        (
            {"selected_option": "baseline", "steps": EXPECTED_STEPS[:-1]},
            "invalid tool trace",
        ),
    ],
)
def test_parent_rejects_untrusted_child_selection_or_trace(
    monkeypatch: pytest.MonkeyPatch,
    child_receipt: dict[str, Any],
    message: str,
) -> None:
    monkeypatch.setattr(
        candidate_v2,
        "_run_rank1_v2_process",
        lambda _payload: child_receipt,
    )

    with pytest.raises(RuntimeError, match=message):
        run_rank1_evidence_v2(json.dumps(_payload()))


def _random_payload(rng: random.Random, case_index: int) -> dict[str, Any]:
    zones = ("east", "north", "south")
    items = ("blankets", "milk", "oats", "rice")
    request_count = rng.randrange(0, 9)
    stock_count = rng.randrange(0, 9)
    volunteer_count = rng.randrange(0, 6)
    requests = []
    for index in range(request_count):
        selected_items = rng.sample(items, rng.randrange(1, 4))
        requests.append(
            _request(
                f"req-{index + 1}",
                rng.choice(zones),
                rng.randrange(1, 6),
                *((item, rng.randrange(1, 5)) for item in selected_items),
            )
        )
    stock = [
        _stock(
            f"lot-{index + 1}",
            rng.choice(items),
            rng.randrange(1, 7),
            rng.choice(("2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24")),
        )
        for index in range(stock_count)
    ]
    volunteers = [
        _volunteer(
            f"vol-{index + 1}",
            rng.sample(zones, rng.randrange(1, 4)),
            rng.randrange(1, 4),
        )
        for index in range(volunteer_count)
    ]
    payload = _payload(requests=requests, stock=stock, volunteers=volunteers)
    payload["case_index"] = case_index
    payload.pop("case_index")
    return payload


def test_deterministic_500_queue_property_never_chooses_worse_than_control() -> None:
    rng = random.Random(0x5155494554)

    for case_index in range(500):
        payload = json.dumps(_random_payload(rng, case_index))
        session = RecoverySessionV2(payload)
        options = _options(session)
        chosen = min(
            options.values(),
            key=lambda row: (
                -row["allocated_requests"],
                row["unresolved_decisions"],
                row["option_id"],
            ),
        )
        baseline = options["baseline"]

        assert chosen["allocated_requests"] >= baseline["allocated_requests"]
        assert chosen["unresolved_decisions"] <= baseline["unresolved_decisions"]

        session.select(chosen["option_id"])
        receipt = json.loads(session.validate())
        result = json.loads(session.authoritative_result())
        assert receipt["metrics"]["constraint_violations"] == 0
        assert receipt["external_actions"] == result["external_actions"] == []
        assert len(result["plan"]["allocations"]) == chosen["allocated_requests"]
