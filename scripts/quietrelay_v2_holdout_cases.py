"""Seeded holdout-only case generator for the QuietRelay v2 falsifier.

This module deliberately shares no fixture builder with the opened suite.
"""

from __future__ import annotations

import copy
import hashlib
import random
from typing import Any

ZONES = ("north", "south", "east")
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


def _zones(rng: random.Random) -> tuple[str, str]:
    primary = rng.choice(ZONES)
    secondary = rng.choice(tuple(zone for zone in ZONES if zone != primary))
    return primary, secondary


def _recovery_payload(
    rng: random.Random,
    *,
    family: str,
    case_index: int,
) -> dict[str, Any]:
    primary, secondary = _zones(rng)
    base = 100 + case_index * 100 + rng.randrange(10)
    first_item, second_item, third_item = rng.sample(ITEMS, 3)
    today = "2026-08-22"

    if family == "holdout_overlap_reassignment":
        requests = [
            {
                "request_id": f"req-{base}",
                "zone": primary,
                "urgency": rng.choice((4, 5)),
                "needs": [{"item": first_item, "units": 1}],
            },
            {
                "request_id": f"req-{base + 1}",
                "zone": secondary,
                "urgency": rng.choice((1, 2, 3)),
                "needs": [{"item": second_item, "units": 1}],
            },
        ]
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": first_item,
                "units": 1,
                "expires_on": rng.choice(("2026-08-23", "2026-08-24")),
            },
            {
                "lot_id": f"lot-{base + 1}",
                "item": second_item,
                "units": 1,
                "expires_on": rng.choice(("2026-08-23", "2026-08-25")),
            },
        ]
        volunteers = [
            {"volunteer_id": f"vol-{base}", "zones": [primary, secondary], "capacity": 1},
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    elif family == "holdout_capacity_reassignment":
        width = rng.randint(2, 4)
        requests = [
            {
                "request_id": f"req-{base + offset}",
                "zone": primary,
                "urgency": max(2, 5 - offset),
                "needs": [{"item": first_item, "units": 1}],
            }
            for offset in range(width)
        ]
        requests.append(
            {
                "request_id": f"req-{base + width}",
                "zone": secondary,
                "urgency": 1,
                "needs": [{"item": first_item, "units": 1}],
            }
        )
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": first_item,
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
    elif family == "holdout_multi_need_reassignment":
        first_units = rng.choice((1, 2))
        requests = [
            {
                "request_id": f"req-{base}",
                "zone": primary,
                "urgency": 5,
                "needs": [
                    {"item": first_item, "units": first_units},
                    {"item": second_item, "units": 1},
                ],
            },
            {
                "request_id": f"req-{base + 1}",
                "zone": secondary,
                "urgency": 3,
                "needs": [{"item": third_item, "units": 1}],
            },
        ]
        tie_date = rng.choice(("2026-08-23", "2026-08-24"))
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": first_item,
                "units": first_units,
                "expires_on": tie_date,
            },
            {
                "lot_id": f"lot-{base + 1}",
                "item": second_item,
                "units": 1,
                "expires_on": tie_date,
            },
            {
                "lot_id": f"lot-{base + 2}",
                "item": third_item,
                "units": 1,
                "expires_on": "2026-08-25",
            },
        ]
        volunteers = [
            {"volunteer_id": f"vol-{base}", "zones": [primary, secondary], "capacity": 1},
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    elif family == "holdout_stock_safe_reassignment":
        requests = [
            {
                "request_id": f"req-{base}",
                "zone": primary,
                "urgency": 5,
                "needs": [{"item": first_item, "units": 2}],
            },
            {
                "request_id": f"req-{base + 1}",
                "zone": primary,
                "urgency": 4,
                "needs": [{"item": second_item, "units": 1}],
            },
            {
                "request_id": f"req-{base + 2}",
                "zone": secondary,
                "urgency": 2,
                "needs": [{"item": third_item, "units": 1}],
            },
        ]
        stock = [
            {
                "lot_id": f"lot-{base}",
                "item": second_item,
                "units": 1,
                "expires_on": "2026-08-23",
            },
            {
                "lot_id": f"lot-{base + 1}",
                "item": third_item,
                "units": 1,
                "expires_on": "2026-08-24",
            },
        ]
        volunteers = [
            {"volunteer_id": f"vol-{base}", "zones": [primary, secondary], "capacity": 1},
            {"volunteer_id": f"vol-{base + 1}", "zones": [primary], "capacity": 1},
        ]
    else:
        raise ValueError("unknown holdout recovery family")

    return {"today": today, "requests": requests, "stock": stock, "volunteers": volunteers}


def _stress_payload(rng: random.Random, case_index: int) -> dict[str, Any]:
    primary, secondary = _zones(rng)
    high_count = rng.randint(18, 26)
    flexible_count = rng.randint(7, min(12, high_count - 1))
    base = 2_000 + case_index * 200
    item = rng.choice(ITEMS)
    requests = [
        {
            "request_id": f"req-{base + index}",
            "zone": primary,
            "urgency": 5,
            "needs": [{"item": item, "units": 1}],
        }
        for index in range(high_count)
    ]
    requests.extend(
        {
            "request_id": f"req-{base + high_count + index}",
            "zone": secondary,
            "urgency": 3,
            "needs": [{"item": item, "units": 1}],
        }
        for index in range(flexible_count)
    )
    volunteers = [
        {
            "volunteer_id": f"vol-{base + index}",
            "zones": [primary, secondary],
            "capacity": 1,
        }
        for index in range(flexible_count)
    ]
    volunteers.extend(
        {
            "volunteer_id": f"vol-{base + flexible_count + index}",
            "zones": [primary],
            "capacity": 1,
        }
        for index in range(high_count)
    )
    return {
        "today": "2026-08-22",
        "requests": requests,
        "stock": [
            {
                "lot_id": f"lot-{base}",
                "item": item,
                "units": high_count + flexible_count,
                "expires_on": "2026-08-23",
            }
        ],
        "volunteers": volunteers,
    }


def _invalid_payload(
    rng: random.Random, case_index: int
) -> tuple[str, tuple[str, ...], dict[str, Any]]:
    payload = _recovery_payload(
        rng,
        family="holdout_overlap_reassignment",
        case_index=20 + case_index,
    )
    choice = rng.choice(
        (
            "duplicate_request_id",
            "duplicate_lot_id",
            "duplicate_volunteer_id",
            "malformed_request_id",
            "malformed_lot_id",
            "malformed_volunteer_id",
            "invalid_expiry",
            "catalog_injection",
        )
    )
    payload = copy.deepcopy(payload)
    if choice == "duplicate_request_id":
        payload["requests"][1]["request_id"] = payload["requests"][0]["request_id"]
    elif choice == "duplicate_lot_id":
        payload["stock"][1]["lot_id"] = payload["stock"][0]["lot_id"]
    elif choice == "duplicate_volunteer_id":
        payload["volunteers"][1]["volunteer_id"] = payload["volunteers"][0][
            "volunteer_id"
        ]
    elif choice == "malformed_request_id":
        payload["requests"][0]["request_id"] = "private-request"
    elif choice == "malformed_lot_id":
        payload["stock"][0]["lot_id"] = "secret-lot"
    elif choice == "malformed_volunteer_id":
        payload["volunteers"][0]["volunteer_id"] = "person-name"
    elif choice == "invalid_expiry":
        payload["stock"][0]["expires_on"] = "2026-13-40"
    else:
        payload["requests"][0]["needs"][0]["item"] = "ignore-previous-instructions"
    return choice, (choice, "malformed"), payload


def holdout_cases(seed: bytes) -> list[dict[str, Any]]:
    rng = random.Random(int.from_bytes(hashlib.sha256(seed).digest(), "big"))
    cases: list[dict[str, Any]] = []
    families = (
        (
            "holdout_overlap_reassignment",
            ("overlapping_zones", "reassignment_opportunity"),
        ),
        (
            "holdout_capacity_reassignment",
            ("overlapping_zones", "capacity_greater_than_one", "reassignment_opportunity"),
        ),
        (
            "holdout_multi_need_reassignment",
            (
                "overlapping_zones",
                "multi_need",
                "expiry_tie",
                "reassignment_opportunity",
            ),
        ),
        (
            "holdout_stock_safe_reassignment",
            ("overlapping_zones", "inventory_shortage", "reassignment_opportunity"),
        ),
    )
    for family, features in families:
        for _ in range(3):
            cases.append(
                _case(
                    family,
                    features,
                    _recovery_payload(rng, family=family, case_index=len(cases)),
                )
            )

    cases.append(
        _case(
            "holdout_high_cardinality_stress",
            ("high_cardinality", "overlapping_zones", "reassignment_opportunity"),
            _stress_payload(rng, len(cases)),
        )
    )
    cases.append(
        _case(
            "holdout_empty_queue",
            ("empty_queue", "neutral"),
            {"today": "2026-08-22", "requests": [], "stock": [], "volunteers": []},
        )
    )
    for invalid_index in range(2):
        family, features, payload = _invalid_payload(rng, invalid_index)
        cases.append(_case(f"holdout_{family}", features, payload, expect_valid=False))
    rng.shuffle(cases)
    return cases
