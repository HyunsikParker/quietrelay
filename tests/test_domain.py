from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta

import pytest

from quietrelay.domain import (
    MAX_TOTAL_NEEDS,
    CommunityRequest,
    Need,
    StockLot,
    Volunteer,
    plan_day,
)

TODAY = date(2026, 8, 22)


def test_plan_uses_earliest_expiring_stock_first() -> None:
    plan = plan_day(
        (CommunityRequest("req-1", "north", 4, (Need("rice", 3),)),),
        (
            StockLot("lot-2", "rice", 3, TODAY + timedelta(days=10)),
            StockLot("lot-1", "rice", 2, TODAY + timedelta(days=1)),
        ),
        (Volunteer("vol-1", ("north",), 1),),
        today=TODAY,
    )

    assert not plan.reviews
    assert [(item.lot_id, item.units) for item in plan.allocations[0].items] == [
        ("lot-1", 2),
        ("lot-2", 1),
    ]


def test_shortage_becomes_review_without_partial_execution() -> None:
    plan = plan_day(
        (CommunityRequest("req-1", "north", 5, (Need("rice", 3),)),),
        (StockLot("lot-1", "rice", 2, TODAY + timedelta(days=2)),),
        (Volunteer("vol-1", ("north",), 1),),
        today=TODAY,
    )

    assert not plan.allocations
    assert plan.reviews[0].reason == "inventory_shortage"
    assert plan.reviews[0].evidence == ("rice: need 3, available 2",)


def test_missing_zone_capacity_becomes_review() -> None:
    plan = plan_day(
        (CommunityRequest("req-1", "south", 3, (Need("rice", 1),)),),
        (StockLot("lot-1", "rice", 1, TODAY + timedelta(days=2)),),
        (Volunteer("vol-1", ("north",), 1),),
        today=TODAY,
    )

    assert not plan.allocations
    assert plan.reviews[0].reason == "volunteer_capacity"


def test_domain_objects_have_no_direct_identity_fields() -> None:
    field_names = {field.name for model in (CommunityRequest, Volunteer) for field in fields(model)}
    assert not field_names & {"name", "email", "phone", "address", "member_name"}


def test_duplicate_identifiers_fail_closed() -> None:
    request = CommunityRequest("req-1", "north", 3, (Need("rice", 1),))
    with pytest.raises(ValueError, match="duplicate request id"):
        plan_day(
            (request, request),
            (StockLot("lot-1", "rice", 2, TODAY + timedelta(days=2)),),
            (Volunteer("vol-1", ("north",), 2),),
            today=TODAY,
        )


def test_duplicate_need_items_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate need item"):
        CommunityRequest("req-1", "north", 3, (Need("rice", 1), Need("rice", 2)))


def test_direct_domain_objects_reject_wrong_runtime_types() -> None:
    with pytest.raises(ValueError):
        Need("rice", True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CommunityRequest("req-1", "north", 3, [Need("rice", 1)])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Volunteer("vol-1", ["north"], 1)  # type: ignore[arg-type]


def test_planner_rejects_excessive_aggregate_needs() -> None:
    needs = tuple(Need(item, 1) for item in ("blankets", "milk", "oats", "rice"))
    requests = tuple(
        CommunityRequest(f"req-{index:04d}", "north", 1, needs)
        for index in range(MAX_TOTAL_NEEDS // len(needs) + 1)
    )

    with pytest.raises(ValueError, match="too many total needs"):
        plan_day(
            requests,
            (StockLot("lot-1", "rice", 1, TODAY + timedelta(days=1)),),
            (Volunteer("vol-1", ("north",), 1),),
            today=TODAY,
        )


def test_oversized_collection_rejects_before_element_access() -> None:
    class ExplodingRecord:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"unexpected access: {name}")

    requests = tuple(ExplodingRecord() for _ in range(1_001))

    with pytest.raises(ValueError, match="too many requests"):
        plan_day(  # type: ignore[arg-type]
            requests,
            (),
            (),
            today=TODAY,
        )
