"""Deterministic, privacy-minimizing planning tools for QuietRelay."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

MAX_RECORDS = 1_000
MAX_UNITS = 10_000
MAX_TOTAL_NEEDS = 3_000
MAX_ZONES_PER_VOLUNTEER = 8

ALLOWED_ITEMS = frozenset({"blankets", "milk", "oats", "rice"})
ALLOWED_ZONES = frozenset({"east", "north", "south"})

_ID_PATTERNS = {
    "request_id": re.compile(r"req-[0-9]{1,4}\Z"),
    "lot_id": re.compile(r"lot-[0-9]{1,4}\Z"),
    "volunteer_id": re.compile(r"vol-[0-9]{1,4}\Z"),
}


def _canonical_id(value: object, *, kind: str) -> str:
    if not isinstance(value, str) or _ID_PATTERNS[kind].fullmatch(value) is None:
        raise ValueError(f"invalid {kind}")
    return value


def _catalog_value(value: object, *, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"invalid {label}")
    return value


def _bounded_integer(value: object, *, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"invalid {label}")
    return value


@dataclass(frozen=True, slots=True)
class Need:
    item: str
    units: int

    def __post_init__(self) -> None:
        _catalog_value(self.item, allowed=ALLOWED_ITEMS, label="need item")
        _bounded_integer(self.units, minimum=1, maximum=MAX_UNITS, label="need units")


@dataclass(frozen=True, slots=True)
class CommunityRequest:
    request_id: str
    zone: str
    urgency: int
    needs: tuple[Need, ...]

    def __post_init__(self) -> None:
        _canonical_id(self.request_id, kind="request_id")
        _catalog_value(self.zone, allowed=ALLOWED_ZONES, label="request zone")
        _bounded_integer(self.urgency, minimum=1, maximum=5, label="request urgency")
        if (
            not isinstance(self.needs, tuple)
            or not self.needs
            or len(self.needs) > 50
            or any(not isinstance(need, Need) for need in self.needs)
        ):
            raise ValueError("invalid request needs")
        if len({need.item for need in self.needs}) != len(self.needs):
            raise ValueError("duplicate need item")


@dataclass(frozen=True, slots=True)
class StockLot:
    lot_id: str
    item: str
    units: int
    expires_on: date

    def __post_init__(self) -> None:
        _canonical_id(self.lot_id, kind="lot_id")
        _catalog_value(self.item, allowed=ALLOWED_ITEMS, label="stock item")
        _bounded_integer(self.units, minimum=1, maximum=MAX_UNITS, label="stock units")
        if type(self.expires_on) is not date:
            raise ValueError("invalid stock expiry")


@dataclass(frozen=True, slots=True)
class Volunteer:
    volunteer_id: str
    zones: tuple[str, ...]
    capacity: int

    def __post_init__(self) -> None:
        _canonical_id(self.volunteer_id, kind="volunteer_id")
        if (
            not isinstance(self.zones, tuple)
            or not 1 <= len(self.zones) <= MAX_ZONES_PER_VOLUNTEER
            or any(not isinstance(zone, str) or zone not in ALLOWED_ZONES for zone in self.zones)
            or len(set(self.zones)) != len(self.zones)
        ):
            raise ValueError("invalid volunteer zones")
        _bounded_integer(self.capacity, minimum=1, maximum=100, label="volunteer capacity")


@dataclass(frozen=True, slots=True)
class AllocationItem:
    lot_id: str
    item: str
    units: int


@dataclass(frozen=True, slots=True)
class Allocation:
    request_id: str
    volunteer_id: str
    items: tuple[AllocationItem, ...]


@dataclass(frozen=True, slots=True)
class ReviewItem:
    request_id: str
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Plan:
    allocations: tuple[Allocation, ...]
    reviews: tuple[ReviewItem, ...]


def _bounded(records: object, label: str, expected_type: type) -> None:
    if not isinstance(records, tuple):
        raise ValueError(f"invalid {label}")
    if len(records) > MAX_RECORDS:
        raise ValueError(f"too many {label}")
    if any(not isinstance(record, expected_type) for record in records):
        raise ValueError(f"invalid {label}")


def plan_day(
    requests: tuple[CommunityRequest, ...],
    stock: tuple[StockLot, ...],
    volunteers: tuple[Volunteer, ...],
    *,
    today: date,
) -> Plan:
    """Allocate clear cases and surface only shortages or capacity conflicts."""
    _bounded(requests, "requests", CommunityRequest)
    _bounded(stock, "stock lots", StockLot)
    _bounded(volunteers, "volunteers", Volunteer)
    if type(today) is not date:
        raise ValueError("invalid planning date")
    if sum(len(row.needs) for row in requests) > MAX_TOTAL_NEEDS:
        raise ValueError("too many total needs")
    if len({row.request_id for row in requests}) != len(requests):
        raise ValueError("duplicate request id")
    if len({row.lot_id for row in stock}) != len(stock):
        raise ValueError("duplicate lot id")
    if len({row.volunteer_id for row in volunteers}) != len(volunteers):
        raise ValueError("duplicate volunteer id")

    lots_by_item: defaultdict[str, list[StockLot]] = defaultdict(list)
    remaining_lot_units: dict[str, int] = {}
    for lot in stock:
        if lot.expires_on < today:
            continue
        lots_by_item[lot.item].append(lot)
        remaining_lot_units[lot.lot_id] = lot.units
    for lots in lots_by_item.values():
        lots.sort(key=lambda lot: (lot.expires_on, lot.lot_id))

    remaining_capacity = {volunteer.volunteer_id: volunteer.capacity for volunteer in volunteers}
    ordered_volunteers = tuple(sorted(volunteers, key=lambda row: row.volunteer_id))
    allocations: list[Allocation] = []
    reviews: list[ReviewItem] = []

    for request in sorted(requests, key=lambda row: (-row.urgency, row.request_id)):
        tentative: list[AllocationItem] = []
        shortage: list[str] = []
        for need in request.needs:
            available = sum(
                remaining_lot_units[lot.lot_id] for lot in lots_by_item.get(need.item, ())
            )
            if available < need.units:
                shortage.append(f"{need.item}: need {need.units}, available {available}")
                continue
            outstanding = need.units
            for lot in lots_by_item[need.item]:
                take = min(outstanding, remaining_lot_units[lot.lot_id])
                if take:
                    tentative.append(AllocationItem(lot.lot_id, need.item, take))
                    outstanding -= take
                if outstanding == 0:
                    break
        if shortage:
            reviews.append(ReviewItem(request.request_id, "inventory_shortage", tuple(shortage)))
            continue

        volunteer = next(
            (
                row
                for row in ordered_volunteers
                if request.zone in row.zones and remaining_capacity[row.volunteer_id] > 0
            ),
            None,
        )
        if volunteer is None:
            reviews.append(
                ReviewItem(
                    request.request_id,
                    "volunteer_capacity",
                    (f"no remaining volunteer capacity for zone {request.zone}",),
                )
            )
            continue

        for item in tentative:
            remaining_lot_units[item.lot_id] -= item.units
        remaining_capacity[volunteer.volunteer_id] -= 1
        allocations.append(Allocation(request.request_id, volunteer.volunteer_id, tuple(tentative)))

    return Plan(tuple(allocations), tuple(reviews))
