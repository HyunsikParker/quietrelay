"""Strands integration for QuietRelay's deterministic planning boundary."""

from __future__ import annotations

import json
import multiprocessing
import os
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import date
from multiprocessing.connection import Connection
from typing import Any

from ollama import Client
from strands import Agent, tool
from strands.models.ollama import OllamaModel

from .domain import CommunityRequest, Need, StockLot, Volunteer, plan_day

MAX_PAYLOAD_BYTES = 64 * 1024
LOCAL_MODEL_ID = "qwen3:4b-instruct-2507-q4_K_M"
LOCAL_MODEL_DIGEST = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
LOCAL_OLLAMA_HOST = "http://127.0.0.1:11434"
LOCAL_CLIENT_ARGS = {
    "follow_redirects": False,
    "timeout": 30.0,
    "trust_env": False,
}
LOCAL_INVOCATION_LIMITS = {"turns": 4, "output_tokens": 2_048, "total_tokens": 4_096}
LOCAL_WALL_TIMEOUT_SECONDS = 45.0
LOCAL_PROMPT = (
    "Call create_daily_plan once for the prevalidated synthetic work queue. "
    "Then confirm that the local plan was prepared without claiming any external action."
)

TOP_LEVEL_FIELDS = {"today", "requests", "stock", "volunteers"}
REQUEST_FIELDS = {"request_id", "zone", "urgency", "needs"}
NEED_FIELDS = {"item", "units"}
STOCK_FIELDS = {"lot_id", "item", "units", "expires_on"}
VOLUNTEER_FIELDS = {"volunteer_id", "zones", "capacity"}

SYSTEM_PROMPT = """You coordinate synthetic community-service operations.
Use create_daily_plan for every allocation request. Never invent identifiers,
override a review item, or expose raw source records. Summarize completed local
allocations and list the human decisions still required. Do not claim that a
message, purchase, delivery, or real-world dispatch occurred."""


def _object(value: Any, *, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"invalid {label} fields")
    return value


def _list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"invalid {label}")
    return value


def plan_payload(payload: str) -> str:
    """Validate one synthetic payload and return a data-minimized plan."""
    if not isinstance(payload, str) or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("invalid payload size")
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("invalid payload size")
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid payload JSON") from exc
    root = _object(raw, fields=TOP_LEVEL_FIELDS, label="top-level")

    requests = []
    source_request_ids: set[str] = set()
    for current in _list(root["requests"], label="requests"):
        row = _object(current, fields=REQUEST_FIELDS, label="request")
        needs = tuple(
            Need(**_object(need, fields=NEED_FIELDS, label="need"))
            for need in _list(row["needs"], label="needs")
        )
        request = CommunityRequest(
            request_id=row["request_id"],
            zone=row["zone"],
            urgency=row["urgency"],
            needs=needs,
        )
        if request.request_id in source_request_ids:
            raise ValueError("duplicate request id")
        source_request_ids.add(request.request_id)
        requests.append(replace(request, request_id=f"req-{len(requests) + 1}"))

    stock = []
    source_lot_ids: set[str] = set()
    for current in _list(root["stock"], label="stock"):
        row = _object(current, fields=STOCK_FIELDS, label="stock lot")
        try:
            expires_on = date.fromisoformat(row["expires_on"])
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid stock expiry") from exc
        lot = StockLot(
            lot_id=row["lot_id"],
            item=row["item"],
            units=row["units"],
            expires_on=expires_on,
        )
        if lot.lot_id in source_lot_ids:
            raise ValueError("duplicate lot id")
        source_lot_ids.add(lot.lot_id)
        stock.append(replace(lot, lot_id=f"lot-{len(stock) + 1}"))

    volunteers = []
    source_volunteer_ids: set[str] = set()
    for current in _list(root["volunteers"], label="volunteers"):
        row = _object(current, fields=VOLUNTEER_FIELDS, label="volunteer")
        volunteer = Volunteer(
            volunteer_id=row["volunteer_id"],
            zones=tuple(_list(row["zones"], label="volunteer zones")),
            capacity=row["capacity"],
        )
        if volunteer.volunteer_id in source_volunteer_ids:
            raise ValueError("duplicate volunteer id")
        source_volunteer_ids.add(volunteer.volunteer_id)
        volunteers.append(replace(volunteer, volunteer_id=f"vol-{len(volunteers) + 1}"))

    try:
        today = date.fromisoformat(root["today"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid planning date") from exc
    plan = plan_day(tuple(requests), tuple(stock), tuple(volunteers), today=today)
    return json.dumps(asdict(plan), separators=(",", ":"), sort_keys=True)


def authoritative_result(payload: str) -> str:
    """Return the deterministic result that is safe to show or record."""
    return json.dumps(
        {"external_actions": [], "plan": json.loads(plan_payload(payload))},
        separators=(",", ":"),
        sort_keys=True,
    )


def _bound_plan_tool(payload: str) -> Any:
    """Bind a validated immutable plan so the model cannot rewrite source data."""
    validated_plan = plan_payload(payload)

    @tool(name="create_daily_plan")
    def create_daily_plan() -> str:
        """Return the prevalidated plan for the current synthetic work queue.

        The application validates source records before the agent runs. This
        tool takes no arguments so the model cannot alter IDs, dates, stock, or
        volunteer capacity while copying data into a tool call.
        """
        return validated_plan

    return create_daily_plan


def _build_agent(payload: str) -> Agent:
    """Build an agent from fixed local configuration only."""
    return Agent(
        model=OllamaModel(
            host=LOCAL_OLLAMA_HOST,
            model_id=LOCAL_MODEL_ID,
            ollama_client_args=LOCAL_CLIENT_ARGS,
            temperature=0.0,
            max_tokens=1_024,
            keep_alive="10m",
        ),
        tools=[_bound_plan_tool(payload)],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
        name="QuietRelay",
        description="Escalation-aware community operations coordinator",
    )


def _verify_local_model(client: Client | None = None) -> None:
    if os.environ.get("OLLAMA_API_KEY"):
        raise ValueError("OLLAMA_API_KEY is not allowed in local-only mode")
    current = client or Client(host=LOCAL_OLLAMA_HOST, **LOCAL_CLIENT_ARGS)
    matches = [model for model in current.list().models if model.model == LOCAL_MODEL_ID]
    if len(matches) != 1 or matches[0].digest != LOCAL_MODEL_DIGEST:
        raise ValueError("approved local model digest is unavailable")


def _exercise_local_agent(payload: str, connection: Connection) -> None:
    try:
        _verify_local_model()
        _build_agent(payload)(LOCAL_PROMPT, limits=LOCAL_INVOCATION_LIMITS)
        connection.send("ok")
    except BaseException:  # Child reports failure without returning payload-derived text.
        connection.send("error")
    finally:
        connection.close()


def _run_agent_process(
    payload: str,
    *,
    timeout: float = LOCAL_WALL_TIMEOUT_SECONDS,
    process_target: Callable[[str, Connection], None] = _exercise_local_agent,
) -> None:
    if timeout <= 0:
        raise ValueError("invalid local agent timeout")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=process_target, args=(payload, send), daemon=True)
    process.start()
    send.close()
    status = "error"
    timed_out = False
    try:
        if not receive.poll(timeout):
            timed_out = True
        else:
            try:
                status = receive.recv()
            except EOFError:
                status = "error"
    finally:
        receive.close()
    if timed_out and process.is_alive():
        process.terminate()
    process.join(5)
    if process.is_alive():
        process.kill()
        process.join(5)
    exit_code = process.exitcode
    process.close()
    if timed_out:
        raise TimeoutError("local agent exceeded its wall-clock limit")
    if status != "ok" or exit_code != 0:
        raise RuntimeError("local agent exercise failed")


def run_local_plan(payload: str) -> str:
    """Exercise the local agent under a hard deadline and return authoritative JSON."""
    result = authoritative_result(payload)
    _run_agent_process(payload)
    return result
