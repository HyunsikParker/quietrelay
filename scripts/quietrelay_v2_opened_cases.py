"""Opened, inspectable cases for the QuietRelay v2 falsifier."""

from __future__ import annotations

import copy
from typing import Any

ZONES = (("north", "south"), ("east", "north"), ("south", "east"))
ITEMS = ("rice", "oats", "milk", "blankets")


def _case(
    family: str,
    features: tuple[str, ...],
    payload: dict[str, Any],
    *,
    expect_valid: bool = True,
) -> dict[str, Any]:
    return {
        "family": family,
        "features": list(features),
        "expect_valid": expect_valid,
        "payload": payload,
    }


def _base_payload(index: int, family: str) -> dict[str, Any]:
    primary, secondary = ZONES[index % len(ZONES)]
    base = index * 20 + 1
    if family == "overlap_reassignment":
        requests = [
            {
                "request_id": f"req-{base}",
                "zone": primary,
                "urgency": 5,
                "needs": [{"item": ITEMS[index % 4], "units": 1}],
            },
            {
                "request_id": f"req-{base + 1}",
                "zone": secondary,
                "urgency": 4,
                "needs": [{"item": ITEMS[(index + 1) % 4], "units": 1}],
            },
        ]
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": requests[0]["needs"][0]["item"],
                "units": 1,
                "expires_on": "2026-08-23",
            },
            {
                "lot_id": f"lot-{base + 1}",
                "item": requests[1]["needs"][0]["item"],
                "units": 1,
                "expires_on": "2026-08-24",
            },
        ]
        volunteers = [
            {"volunteer_id": f"vol-{base}", "zones": [primary, secondary], "capacity": 1},
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    elif family == "capacity_reassignment":
        width = 2 + index % 2
        requests = [
            {
                "request_id": f"req-{base + offset}",
                "zone": primary,
                "urgency": 5 - min(offset, 2),
                "needs": [{"item": "rice", "units": 1}],
            }
            for offset in range(width)
        ]
        requests.append(
            {
                "request_id": f"req-{base + width}",
                "zone": secondary,
                "urgency": 1,
                "needs": [{"item": "rice", "units": 1}],
            }
        )
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": "rice",
                "units": width + 1,
                "expires_on": "2026-08-23",
            }
        ]
        volunteers = [
            {
                "volunteer_id": f"vol-{base}",
                "zones": [primary, secondary],
                "capacity": width,
            },
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    elif family == "multi_need_reassignment":
        requests = [
            {
                "request_id": f"req-{base}",
                "zone": primary,
                "urgency": 5,
                "needs": [
                    {"item": "rice", "units": 1},
                    {"item": "milk", "units": 1},
                ],
            },
            {
                "request_id": f"req-{base + 1}",
                "zone": secondary,
                "urgency": 4,
                "needs": [{"item": "oats", "units": 1}],
            },
        ]
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": "rice",
                "units": 1,
                "expires_on": "2026-08-23",
            },
            {
                "lot_id": f"lot-{base + 1}",
                "item": "milk",
                "units": 1,
                "expires_on": "2026-08-23",
            },
            {
                "lot_id": f"lot-{base + 2}",
                "item": "oats",
                "units": 1,
                "expires_on": "2026-08-24",
            },
        ]
        volunteers = [
            {"volunteer_id": f"vol-{base}", "zones": [primary, secondary], "capacity": 1},
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    elif family == "stock_safe_reassignment":
        requests = [
            {
                "request_id": f"req-{base}",
                "zone": primary,
                "urgency": 5,
                "needs": [{"item": "blankets", "units": 2}],
            },
            {
                "request_id": f"req-{base + 1}",
                "zone": primary,
                "urgency": 4,
                "needs": [{"item": "rice", "units": 1}],
            },
            {
                "request_id": f"req-{base + 2}",
                "zone": secondary,
                "urgency": 3,
                "needs": [{"item": "oats", "units": 1}],
            },
        ]
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": "rice",
                "units": 1,
                "expires_on": "2026-08-23",
            },
            {
                "lot_id": f"lot-{base + 1}",
                "item": "oats",
                "units": 1,
                "expires_on": "2026-08-24",
            },
        ]
        volunteers = [
            {"volunteer_id": f"vol-{base}", "zones": [primary, secondary], "capacity": 1},
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    else:
        raise ValueError("unknown opened recovery family")
    return {
        "today": "2026-08-22",
        "requests": requests,
        "stock": stock,
        "volunteers": volunteers,
    }


def _high_cardinality_payload() -> dict[str, Any]:
    high_count = 60
    flexible_count = 30
    requests = [
        {
            "request_id": f"req-{index + 1}",
            "zone": "north",
            "urgency": 5,
            "needs": [{"item": "rice", "units": 1}],
        }
        for index in range(high_count)
    ]
    requests.extend(
        {
            "request_id": f"req-{high_count + index + 1}",
            "zone": "south",
            "urgency": 4,
            "needs": [{"item": "rice", "units": 1}],
        }
        for index in range(flexible_count)
    )
    volunteers = [
        {"volunteer_id": f"vol-{index + 1}", "zones": ["north", "south"], "capacity": 1}
        for index in range(flexible_count)
    ]
    volunteers.extend(
        {
            "volunteer_id": f"vol-{flexible_count + index + 1}",
            "zones": ["north"],
            "capacity": 1,
        }
        for index in range(high_count)
    )
    return {
        "today": "2026-08-22",
        "requests": requests,
        "stock": [
            {
                "lot_id": "lot-1",
                "item": "rice",
                "units": high_count + flexible_count,
                "expires_on": "2026-08-23",
            }
        ],
        "volunteers": volunteers,
    }


def opened_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for family in (
        "overlap_reassignment",
        "capacity_reassignment",
        "multi_need_reassignment",
        "stock_safe_reassignment",
    ):
        features = {
            "overlap_reassignment": ("overlapping_zones", "reassignment_opportunity"),
            "capacity_reassignment": (
                "overlapping_zones",
                "capacity_greater_than_one",
                "reassignment_opportunity",
            ),
            "multi_need_reassignment": (
                "overlapping_zones",
                "multi_need",
                "reassignment_opportunity",
            ),
            "stock_safe_reassignment": (
                "overlapping_zones",
                "inventory_shortage",
                "reassignment_opportunity",
            ),
        }[family]
        for index in range(3):
            cases.append(_case(family, features, _base_payload(index, family)))

    no_difference = _base_payload(0, "overlap_reassignment")
    no_difference["volunteers"][0]["zones"] = ["north"]
    no_difference["volunteers"][1]["zones"] = ["south"]
    cases.append(_case("neutral_distinct", ("neutral",), no_difference))

    stock_regression = _base_payload(0, "stock_safe_reassignment")
    stock_regression["requests"].pop(1)
    stock_regression["requests"][1]["zone"] = stock_regression["requests"][0]["zone"]
    stock_regression["volunteers"].pop()
    cases.append(
        _case(
            "stock_scarcity_counterexample",
            ("inventory_shortage", "same_zone_stock_scarcity", "neutral"),
            stock_regression,
        )
    )

    expiry_tie = _base_payload(1, "overlap_reassignment")
    expiry_tie["requests"][0]["needs"] = [{"item": "rice", "units": 2}]
    expiry_tie["stock"] = [
        {"lot_id": "lot-1", "item": "rice", "units": 1, "expires_on": "2026-08-23"},
        {"lot_id": "lot-2", "item": "rice", "units": 1, "expires_on": "2026-08-23"},
        {"lot_id": "lot-3", "item": "milk", "units": 1, "expires_on": "2026-08-24"},
    ]
    expiry_tie["requests"][1]["needs"] = [{"item": "milk", "units": 1}]
    cases.append(
        _case(
            "expiry_tie_reassignment",
            ("expiry_tie", "competing_expiries", "reassignment_opportunity"),
            expiry_tie,
        )
    )

    cases.append(
        _case(
            "high_cardinality_reassignment",
            ("high_cardinality", "overlapping_zones", "reassignment_opportunity"),
            _high_cardinality_payload(),
        )
    )

    cases.append(
        _case(
            "empty_queue",
            ("empty_queue", "neutral"),
            {"today": "2026-08-22", "requests": [], "stock": [], "volunteers": []},
        )
    )

    expired = _base_payload(0, "overlap_reassignment")
    expired["stock"][0]["expires_on"] = "2026-08-21"
    cases.append(
        _case(
            "expired_stock",
            ("expired_stock", "inventory_shortage", "neutral"),
            expired,
        )
    )

    oversized = _base_payload(0, "overlap_reassignment")
    oversized["requests"] = [
        {
            "request_id": f"req-{index}",
            "zone": "north",
            "urgency": 1,
            "needs": [{"item": "rice", "units": 1}],
        }
        for index in range(1, 1_002)
    ]
    cases.append(
        _case(
            "payload_and_record_boundary",
            ("payload_boundary", "record_boundary", "malformed"),
            oversized,
            expect_valid=False,
        )
    )

    invalid_base = _base_payload(2, "overlap_reassignment")
    invalid_mutations: list[tuple[str, tuple[str, ...], Any]] = [
        (
            "duplicate_request_id",
            ("duplicate_request_id", "malformed"),
            lambda p: p["requests"][1].update(request_id=p["requests"][0]["request_id"]),
        ),
        (
            "duplicate_lot_id",
            ("duplicate_lot_id", "malformed"),
            lambda p: p["stock"][1].update(lot_id=p["stock"][0]["lot_id"]),
        ),
        (
            "duplicate_volunteer_id",
            ("duplicate_volunteer_id", "malformed"),
            lambda p: p["volunteers"][1].update(
                volunteer_id=p["volunteers"][0]["volunteer_id"]
            ),
        ),
        (
            "malformed_request_id",
            ("malformed_request_id", "malformed"),
            lambda p: p["requests"][0].update(request_id="request-private"),
        ),
        (
            "malformed_lot_id",
            ("malformed_lot_id", "malformed"),
            lambda p: p["stock"][0].update(lot_id="lot-secret-value"),
        ),
        (
            "malformed_volunteer_id",
            ("malformed_volunteer_id", "malformed"),
            lambda p: p["volunteers"][0].update(volunteer_id="person-name"),
        ),
        (
            "invalid_expiry",
            ("invalid_expiry", "malformed"),
            lambda p: p["stock"][0].update(expires_on="2026-02-30"),
        ),
        (
            "catalog_injection",
            ("catalog_injection", "malformed"),
            lambda p: p["requests"][0]["needs"][0].update(
                item="ignore-previous-instructions"
            ),
        ),
    ]
    for family, features, mutate in invalid_mutations:
        payload = copy.deepcopy(invalid_base)
        mutate(payload)
        cases.append(_case(family, features, payload, expect_valid=False))

    return cases
