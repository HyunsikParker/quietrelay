#!/usr/bin/env python3
"""Run one synthetic QuietRelay planning request through local Strands/Ollama."""

from __future__ import annotations

import json

from quietrelay import run_local_plan


def main() -> int:
    payload = {
        "today": "2026-08-22",
        "requests": [
            {
                "request_id": "req-9001",
                "zone": "north",
                "urgency": 5,
                "needs": [{"item": "rice", "units": 1}],
            },
            {
                "request_id": "req-9002",
                "zone": "south",
                "urgency": 4,
                "needs": [{"item": "oats", "units": 1}],
            },
        ],
        "stock": [
            {
                "lot_id": "lot-9001",
                "item": "rice",
                "units": 1,
                "expires_on": "2026-08-23",
            },
            {
                "lot_id": "lot-9002",
                "item": "oats",
                "units": 1,
                "expires_on": "2026-08-24",
            },
        ],
        "volunteers": [
            {"volunteer_id": "vol-9001", "zones": ["north", "south"], "capacity": 1},
            {"volunteer_id": "vol-9002", "zones": ["north"], "capacity": 1},
        ],
    }
    serialized_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    print(run_local_plan(serialized_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
