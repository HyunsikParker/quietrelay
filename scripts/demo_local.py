#!/usr/bin/env python3
"""Run one synthetic QuietRelay planning request through local Strands/Ollama."""

from __future__ import annotations

import json

from quietrelay.agent import run_local_plan


def main() -> int:
    payload = {
        "today": "2026-08-22",
        "requests": [
            {
                "request_id": "req-9001",
                "zone": "north",
                "urgency": 5,
                "needs": [{"item": "rice", "units": 2}],
            }
        ],
        "stock": [
            {
                "lot_id": "lot-9001",
                "item": "rice",
                "units": 2,
                "expires_on": "2026-08-23",
            }
        ],
        "volunteers": [{"volunteer_id": "vol-9001", "zones": ["north"], "capacity": 1}],
    }
    serialized_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    print(run_local_plan(serialized_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
