"""Keep accepted queue sizes from multiplying the matching graph's memory use."""

import json
import tracemalloc

from quietrelay.agent import MAX_PAYLOAD_BYTES
from quietrelay.rank1_candidate_v2 import _canonical_records, _slot_graph


def test_dense_valid_queue_keeps_graph_under_twelve_mib() -> None:
    payload = json.dumps(
        {
            "today": "2026-09-10",
            "requests": [
                {
                    "request_id": f"req-{index + 1}",
                    "zone": "north",
                    "urgency": 3,
                    "needs": [{"item": "rice", "units": 1}],
                }
                for index in range(300)
            ],
            "stock": [],
            "volunteers": [
                {
                    "volunteer_id": f"vol-{index + 1}",
                    "zones": ["north"],
                    "capacity": 100,
                }
                for index in range(350)
            ],
        },
        separators=(",", ":"),
    )
    assert len(payload.encode()) < MAX_PAYLOAD_BYTES
    records = _canonical_records(payload)
    tracemalloc.start()
    try:
        graph = _slot_graph(records)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(graph) == 300
    assert all(len(candidates) == 35_000 for candidates in graph.values())
    # The former per-request copies exceeded 80 MiB; allow ample interpreter overhead.
    assert peak < 12 * 1024 * 1024
