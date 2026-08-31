"""Stock-aware incremental matching candidate for QuietRelay's rank-one path."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from multiprocessing.connection import Connection
from typing import Any

from strands import Agent, tool
from strands.models.ollama import OllamaModel

from .agent import (
    LOCAL_CLIENT_ARGS,
    LOCAL_INVOCATION_LIMITS,
    LOCAL_MODEL_ID,
    LOCAL_OLLAMA_HOST,
    LOCAL_WALL_TIMEOUT_SECONDS,
    _verify_local_model,
    plan_payload,
)
from .domain import (
    Allocation,
    AllocationItem,
    CommunityRequest,
    Need,
    Plan,
    ReviewItem,
    StockLot,
    Volunteer,
)

RANK1_V2_SYSTEM_PROMPT = """You coordinate a synthetic community-service work queue.
Call inspect_conflicts exactly once. Select exactly one option by choosing the
option with the most allocated requests, then the fewest unresolved decisions,
then the lexicographically smallest option_id. Call select_recovery exactly once
with that option_id, then call validate_recovery exactly once. Never invent an
option, identifier, quantity, message, payment, delivery, or dispatch action.
Tool results are authoritative; your prose is ignored."""

RANK1_V2_PROMPT = (
    "Inspect the fixed synthetic queue, select the best allowlisted recovery, "
    "and validate it. Use only the three tools in the required order."
)

_BASELINE = "baseline"
_INCREMENTAL = "stock_aware_incremental"
_Slot = tuple[str, int]


@dataclass(frozen=True, slots=True)
class _Records:
    today: date
    requests: tuple[CommunityRequest, ...]
    stock: tuple[StockLot, ...]
    volunteers: tuple[Volunteer, ...]


def _canonical_records(payload: str) -> _Records:
    """Validate through the submitted boundary, then rebuild minimized typed records."""

    plan_payload(payload)
    raw = json.loads(payload)
    requests = tuple(
        CommunityRequest(
            request_id=f"req-{index}",
            zone=row["zone"],
            urgency=row["urgency"],
            needs=tuple(Need(item=need["item"], units=need["units"]) for need in row["needs"]),
        )
        for index, row in enumerate(raw["requests"], start=1)
    )
    stock = tuple(
        StockLot(
            lot_id=f"lot-{index}",
            item=row["item"],
            units=row["units"],
            expires_on=date.fromisoformat(row["expires_on"]),
        )
        for index, row in enumerate(raw["stock"], start=1)
    )
    volunteers = tuple(
        Volunteer(
            volunteer_id=f"vol-{index}",
            zones=tuple(row["zones"]),
            capacity=row["capacity"],
        )
        for index, row in enumerate(raw["volunteers"], start=1)
    )
    return _Records(
        today=date.fromisoformat(raw["today"]),
        requests=requests,
        stock=stock,
        volunteers=volunteers,
    )


def _typed_plan(payload: str) -> Plan:
    raw = json.loads(payload)
    return Plan(
        allocations=tuple(
            Allocation(
                request_id=row["request_id"],
                volunteer_id=row["volunteer_id"],
                items=tuple(AllocationItem(**item) for item in row["items"]),
            )
            for row in raw["allocations"]
        ),
        reviews=tuple(
            ReviewItem(
                request_id=row["request_id"],
                reason=row["reason"],
                evidence=tuple(row["evidence"]),
            )
            for row in raw["reviews"]
        ),
    )


def _plan_digest(plan: Plan) -> str:
    canonical = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validate_plan(records: _Records, plan: Plan) -> dict[str, Any]:
    request_by_id = {row.request_id: row for row in records.requests}
    volunteer_by_id = {row.volunteer_id: row for row in records.volunteers}
    stock_by_id = {row.lot_id: row for row in records.stock}
    outcomes = [row.request_id for row in plan.allocations] + [
        row.request_id for row in plan.reviews
    ]
    if len(outcomes) != len(set(outcomes)) or set(outcomes) != set(request_by_id):
        raise ValueError("every request must have exactly one outcome")

    volunteer_use: defaultdict[str, int] = defaultdict(int)
    lot_use: defaultdict[str, int] = defaultdict(int)
    for allocation in plan.allocations:
        request = request_by_id.get(allocation.request_id)
        volunteer = volunteer_by_id.get(allocation.volunteer_id)
        if request is None or volunteer is None or request.zone not in volunteer.zones:
            raise ValueError("allocation violates volunteer zone")
        volunteer_use[volunteer.volunteer_id] += 1

        requested = {need.item: need.units for need in request.needs}
        supplied: defaultdict[str, int] = defaultdict(int)
        for item in allocation.items:
            lot = stock_by_id.get(item.lot_id)
            if lot is None or lot.item != item.item or lot.expires_on < records.today:
                raise ValueError("allocation violates stock provenance")
            if item.item not in requested or item.units <= 0:
                raise ValueError("allocation contains an unrequested item")
            supplied[item.item] += item.units
            lot_use[item.lot_id] += item.units
        if dict(supplied) != requested:
            raise ValueError("allocation does not exactly satisfy requested units")

    for volunteer_id, used in volunteer_use.items():
        if used > volunteer_by_id[volunteer_id].capacity:
            raise ValueError("allocation exceeds volunteer capacity")
    for lot_id, used in lot_use.items():
        if used > stock_by_id[lot_id].units:
            raise ValueError("allocation exceeds stock")
    if any(
        review.reason not in {"inventory_shortage", "volunteer_capacity"}
        for review in plan.reviews
    ):
        raise ValueError("review reason is not allowlisted")

    request_count = len(records.requests)
    return {
        "allocated_requests": len(plan.allocations),
        "unresolved_decisions": len(plan.reviews),
        "allocation_coverage": len(plan.allocations) / request_count if request_count else 1.0,
        "constraint_violations": 0,
        "external_actions": [],
        "plan_sha256": _plan_digest(plan),
    }


def _stock_index(
    records: _Records,
) -> tuple[dict[str, list[StockLot]], dict[str, int]]:
    lots_by_item: defaultdict[str, list[StockLot]] = defaultdict(list)
    remaining: dict[str, int] = {}
    for lot in records.stock:
        if lot.expires_on < records.today:
            continue
        lots_by_item[lot.item].append(lot)
        remaining[lot.lot_id] = lot.units
    for lots in lots_by_item.values():
        lots.sort(key=lambda row: (row.expires_on, row.lot_id))
    return dict(lots_by_item), remaining


def _stage_exact_fefo(
    request: CommunityRequest,
    lots_by_item: dict[str, list[StockLot]],
    remaining: dict[str, int],
) -> tuple[tuple[AllocationItem, ...] | None, tuple[str, ...]]:
    """Stage, but do not commit, one request's exact FEFO stock."""

    shortages = tuple(
        f"{need.item}: need {need.units}, available {available}"
        for need in request.needs
        if (
            available := sum(
                remaining[lot.lot_id] for lot in lots_by_item.get(need.item, ())
            )
        )
        < need.units
    )
    if shortages:
        return None, shortages

    staged: list[AllocationItem] = []
    for need in request.needs:
        outstanding = need.units
        for lot in lots_by_item[need.item]:
            take = min(outstanding, remaining[lot.lot_id])
            if take:
                staged.append(AllocationItem(lot.lot_id, need.item, take))
                outstanding -= take
            if outstanding == 0:
                break
    return tuple(staged), ()


def _commit_staged(items: tuple[AllocationItem, ...], remaining: dict[str, int]) -> None:
    for item in items:
        remaining[item.lot_id] -= item.units


def _slot_graph(records: _Records) -> dict[str, tuple[_Slot, ...]]:
    slots_by_zone: defaultdict[str, list[_Slot]] = defaultdict(list)
    for volunteer in sorted(records.volunteers, key=lambda row: row.volunteer_id):
        slots = [
            (volunteer.volunteer_id, slot_index)
            for slot_index in range(volunteer.capacity)
        ]
        for zone in volunteer.zones:
            slots_by_zone[zone].extend(slots)
    return {
        request.request_id: tuple(slots_by_zone.get(request.zone, ()))
        for request in records.requests
    }


def _augment_iteratively(
    request_id: str,
    adjacency: dict[str, tuple[_Slot, ...]],
    slot_to_request: dict[_Slot, str],
    request_to_slot: dict[str, _Slot],
) -> bool:
    """Include request_id via a deterministic, non-recursive augmenting path."""

    queue = deque([request_id])
    seen_requests = {request_id}
    seen_slots: set[_Slot] = set()
    parent_request_by_slot: dict[_Slot, str] = {}
    free_slot: _Slot | None = None

    while queue and free_slot is None:
        current_request = queue.popleft()
        for slot in adjacency[current_request]:
            if slot in seen_slots:
                continue
            seen_slots.add(slot)
            parent_request_by_slot[slot] = current_request
            occupant = slot_to_request.get(slot)
            if occupant is None:
                free_slot = slot
                break
            if occupant not in seen_requests:
                seen_requests.add(occupant)
                queue.append(occupant)

    if free_slot is None:
        return False

    current_slot = free_slot
    while True:
        current_request = parent_request_by_slot[current_slot]
        previous_slot = request_to_slot.get(current_request)
        slot_to_request[current_slot] = current_request
        request_to_slot[current_request] = current_slot
        if previous_slot is None:
            break
        current_slot = previous_slot
    return True


def _stock_aware_incremental_plan(records: _Records) -> Plan:
    """Accept requests in submitted priority order without speculative stock commits."""

    lots_by_item, remaining = _stock_index(records)
    adjacency = _slot_graph(records)
    slot_to_request: dict[_Slot, str] = {}
    request_to_slot: dict[str, _Slot] = {}
    items_by_request: dict[str, tuple[AllocationItem, ...]] = {}
    accepted_order: list[str] = []
    reviews: list[ReviewItem] = []

    ordered_requests = sorted(records.requests, key=lambda row: (-row.urgency, row.request_id))
    for request in ordered_requests:
        staged, shortage = _stage_exact_fefo(request, lots_by_item, remaining)
        if staged is None:
            reviews.append(ReviewItem(request.request_id, "inventory_shortage", shortage))
            continue
        if not _augment_iteratively(
            request.request_id,
            adjacency,
            slot_to_request,
            request_to_slot,
        ):
            reviews.append(
                ReviewItem(
                    request.request_id,
                    "volunteer_capacity",
                    (f"no incremental matching capacity for zone {request.zone}",),
                )
            )
            continue
        _commit_staged(staged, remaining)
        items_by_request[request.request_id] = staged
        accepted_order.append(request.request_id)

    allocations = tuple(
        Allocation(
            request_id=request_id,
            volunteer_id=request_to_slot[request_id][0],
            items=items_by_request[request_id],
        )
        for request_id in accepted_order
    )
    return Plan(allocations=allocations, reviews=tuple(reviews))


def _validate_fefo(records: _Records, plan: Plan) -> dict[str, Any]:
    """Validate typed constraints and independently replay exact FEFO consumption."""

    metrics = _validate_plan(records, plan)
    allocation_by_request = {row.request_id: row for row in plan.allocations}
    review_by_request = {row.request_id: row for row in plan.reviews}
    lots_by_item, remaining = _stock_index(records)

    for request in sorted(records.requests, key=lambda row: (-row.urgency, row.request_id)):
        staged, shortage = _stage_exact_fefo(request, lots_by_item, remaining)
        allocation = allocation_by_request.get(request.request_id)
        review = review_by_request.get(request.request_id)
        if allocation is not None:
            if staged is None or allocation.items != staged:
                raise ValueError("allocation violates exact FEFO staging")
            _commit_staged(staged, remaining)
        elif review is None:
            raise ValueError("request outcome is missing")
        elif review.reason == "inventory_shortage":
            if staged is not None or review.evidence != shortage:
                raise ValueError("inventory review does not match staged stock")
        elif staged is None:
            raise ValueError("capacity review masks an inventory shortage")
    return metrics


def _best_option(metrics: dict[str, dict[str, Any]]) -> str:
    return min(
        metrics,
        key=lambda option_id: (
            -metrics[option_id]["allocated_requests"],
            metrics[option_id]["unresolved_decisions"],
            option_id,
        ),
    )


class RecoverySessionV2:
    """One fixed, stateful, fail-closed three-tool v2 recovery session."""

    def __init__(self, payload: str) -> None:
        self._records = _canonical_records(payload)
        self._plans = {
            _BASELINE: _typed_plan(plan_payload(payload)),
            _INCREMENTAL: _stock_aware_incremental_plan(self._records),
        }
        self._metrics = {
            option_id: _validate_fefo(self._records, plan)
            for option_id, plan in self._plans.items()
        }
        self._best_option = _best_option(self._metrics)
        self._trace: list[dict[str, str]] = []
        self._selected: str | None = None
        self._validated_plan: Plan | None = None
        self._validation_receipt: dict[str, Any] | None = None

    def inspect(self) -> str:
        if self._trace:
            raise ValueError("inspect_conflicts must be first and one-shot")
        self._trace.append({"step": "inspect_conflicts"})
        options = [
            {
                "option_id": option_id,
                "allocated_requests": metrics["allocated_requests"],
                "unresolved_decisions": metrics["unresolved_decisions"],
            }
            for option_id, metrics in sorted(self._metrics.items())
        ]
        return json.dumps({"options": options}, sort_keys=True, separators=(",", ":"))

    def select(self, option_id: str) -> str:
        if self._trace != [{"step": "inspect_conflicts"}]:
            raise ValueError("select_recovery requires one prior inspection")
        if option_id not in self._plans:
            raise ValueError("recovery option is not allowlisted")
        self._selected = option_id
        self._trace.append({"step": "select_recovery", "option_id": option_id})
        metrics = self._metrics[option_id]
        aggregate = {
            "allocated_requests": metrics["allocated_requests"],
            "unresolved_decisions": metrics["unresolved_decisions"],
            "constraint_violations": metrics["constraint_violations"],
        }
        return json.dumps(
            {"option_id": option_id, "metrics": aggregate},
            sort_keys=True,
            separators=(",", ":"),
        )

    def validate(self) -> str:
        if self._selected is None or len(self._trace) != 2:
            raise ValueError("validate_recovery requires one allowlisted selection")
        self._trace.append({"step": "validate_recovery", "option_id": self._selected})
        plan = self._plans[self._selected]
        metrics = _validate_fefo(self._records, plan)
        self._validated_plan = plan
        trace_bytes = json.dumps(self._trace, sort_keys=True, separators=(",", ":")).encode()
        self._validation_receipt = {
            "external_actions": [],
            "selected_option": self._selected,
            "metrics": metrics,
            "audit": {
                "steps": list(self._trace),
                "sha256": hashlib.sha256(trace_bytes).hexdigest(),
            },
        }
        return json.dumps(self._validation_receipt, sort_keys=True, separators=(",", ":"))

    def authoritative_result(self) -> str:
        if self._validated_plan is None:
            raise ValueError("recovery workflow did not validate")
        return json.dumps(
            {"external_actions": [], "plan": asdict(self._validated_plan)},
            sort_keys=True,
            separators=(",", ":"),
        )

    def evidence_result(self) -> str:
        if self._validated_plan is None or self._validation_receipt is None:
            raise ValueError("recovery workflow did not validate")
        return json.dumps(
            {
                "external_actions": [],
                "selected_option": self._validation_receipt["selected_option"],
                "plan": asdict(self._validated_plan),
                "metrics": self._validation_receipt["metrics"],
                "audit": self._validation_receipt["audit"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _sanitized_execution(self) -> dict[str, Any]:
        if self._validation_receipt is None:
            raise ValueError("recovery workflow did not validate")
        return {
            "selected_option": self._validation_receipt["selected_option"],
            "steps": [row["step"] for row in self._validation_receipt["audit"]["steps"]],
        }


def _bound_rank1_tools_v2(session: RecoverySessionV2) -> list[Any]:
    @tool(name="inspect_conflicts")
    def inspect_conflicts() -> str:
        """List only allowlisted option identifiers and bounded aggregate metrics."""

        return session.inspect()

    @tool(name="select_recovery")
    def select_recovery(option_id: str) -> str:
        """Select the policy-best option returned by inspect_conflicts."""

        return session.select(option_id)

    @tool(name="validate_recovery")
    def validate_recovery() -> str:
        """Independently validate the selected plan and return aggregate evidence."""

        return session.validate()

    return [inspect_conflicts, select_recovery, validate_recovery]


def _build_rank1_agent_v2(session: RecoverySessionV2) -> Agent:
    return Agent(
        model=OllamaModel(
            host=LOCAL_OLLAMA_HOST,
            model_id=LOCAL_MODEL_ID,
            ollama_client_args=LOCAL_CLIENT_ARGS,
            temperature=0.0,
            max_tokens=1_024,
            keep_alive="10m",
        ),
        tools=_bound_rank1_tools_v2(session),
        system_prompt=RANK1_V2_SYSTEM_PROMPT,
        callback_handler=None,
        name="QuietRelayRankOneFalsifierV2",
        description="Stock-aware incremental synthetic recovery coordinator",
    )


def _execute_authoritative_path(session: RecoverySessionV2) -> str:
    options = json.loads(session.inspect())["options"]
    selected = min(
        options,
        key=lambda row: (
            -row["allocated_requests"],
            row["unresolved_decisions"],
            row["option_id"],
        ),
    )["option_id"]
    session.select(selected)
    session.validate()
    return session.authoritative_result()


def authoritative_plan_v2(payload: str) -> str:
    """Execute the three typed stages deterministically and return the exact plan schema."""

    return _execute_authoritative_path(RecoverySessionV2(payload))


def _exercise_rank1_v2_agent(payload: str, connection: Connection) -> None:
    try:
        _verify_local_model()
        session = RecoverySessionV2(payload)
        agent = _build_rank1_agent_v2(session)
        agent(RANK1_V2_PROMPT, limits=LOCAL_INVOCATION_LIMITS)
        connection.send(session._sanitized_execution())
    except BaseException:  # Child reports failure without returning payload-derived text.
        connection.send("error")
    finally:
        connection.close()


def _run_rank1_v2_process(
    payload: str,
    *,
    timeout: float = LOCAL_WALL_TIMEOUT_SECONDS,
    process_target: Callable[[str, Connection], None] = _exercise_rank1_v2_agent,
) -> dict[str, Any]:
    if timeout <= 0:
        raise ValueError("invalid local agent timeout")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=process_target, args=(payload, send), daemon=True)
    process.start()
    send.close()
    response: object = "error"
    timed_out = False
    try:
        if not receive.poll(timeout):
            timed_out = True
        else:
            try:
                response = receive.recv()
            except EOFError:
                response = "error"
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
        raise TimeoutError("rank-one local agent exceeded its wall-clock limit")
    if (
        exit_code != 0
        or not isinstance(response, dict)
        or set(response) != {"selected_option", "steps"}
        or not isinstance(response["selected_option"], str)
        or not isinstance(response["steps"], list)
        or any(not isinstance(step, str) for step in response["steps"])
    ):
        raise RuntimeError("rank-one local agent exercise failed")
    return response


def run_rank1_evidence_v2(payload: str) -> str:
    """Run the isolated three-tool path and rebuild sanitized evidence in the parent."""

    session = RecoverySessionV2(payload)
    child_receipt = _run_rank1_v2_process(payload)
    expected_steps = ["inspect_conflicts", "select_recovery", "validate_recovery"]
    if child_receipt["steps"] != expected_steps:
        raise RuntimeError("rank-one local agent returned an invalid tool trace")

    options = json.loads(session.inspect())["options"]
    selected = min(
        options,
        key=lambda row: (
            -row["allocated_requests"],
            row["unresolved_decisions"],
            row["option_id"],
        ),
    )["option_id"]
    if child_receipt["selected_option"] != selected:
        raise RuntimeError("rank-one local agent violated deterministic selection policy")
    session.select(selected)
    session.validate()
    return session.evidence_result()


def run_rank1_plan_v2(payload: str) -> str:
    """Run the evidence path and expose only the existing authoritative plan schema."""

    evidence = json.loads(run_rank1_evidence_v2(payload))
    return json.dumps(
        {"external_actions": evidence["external_actions"], "plan": evidence["plan"]},
        sort_keys=True,
        separators=(",", ":"),
    )
