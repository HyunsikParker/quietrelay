from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[1]


def _load(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_opened_manifest_is_diverse_and_machine_checkable() -> None:
    module = _load("quietrelay_v2_opened_cases", "scripts/quietrelay_v2_opened_cases.py")
    cases = module.opened_cases()
    assert len(cases) == 27
    assert sum(bool(case["expect_valid"]) for case in cases) == 18
    features = Counter(feature for case in cases for feature in case["features"])
    required = {
        "overlapping_zones",
        "capacity_greater_than_one",
        "multi_need",
        "inventory_shortage",
        "same_zone_stock_scarcity",
        "expiry_tie",
        "competing_expiries",
        "expired_stock",
        "empty_queue",
        "high_cardinality",
        "payload_boundary",
        "record_boundary",
        "duplicate_request_id",
        "duplicate_lot_id",
        "duplicate_volunteer_id",
        "malformed_request_id",
        "malformed_lot_id",
        "malformed_volunteer_id",
        "invalid_expiry",
        "catalog_injection",
    }
    assert required <= features.keys()
    assert {
        "overlap_reassignment",
        "capacity_reassignment",
        "multi_need_reassignment",
        "stock_safe_reassignment",
    } <= {case["family"] for case in cases}

    high = next(case for case in cases if case["family"] == "high_cardinality_reassignment")
    oversized = next(case for case in cases if case["family"] == "payload_and_record_boundary")
    assert len(json.dumps(high["payload"], separators=(",", ":")).encode()) < 64 * 1024
    assert len(json.dumps(oversized["payload"], separators=(",", ":")).encode()) > 64 * 1024


def test_holdout_generator_is_separate_seeded_and_not_an_opened_relabel() -> None:
    source = (ROOT / "scripts/quietrelay_v2_holdout_cases.py").read_text()
    assert "quietrelay_v2_opened_cases" not in source
    assert "_base_payload" not in source
    module = _load("quietrelay_v2_holdout_cases", "scripts/quietrelay_v2_holdout_cases.py")
    first = module.holdout_cases(bytes(range(32)))
    replay = module.holdout_cases(bytes(range(32)))
    different = module.holdout_cases(bytes(reversed(range(32))))
    assert first == replay
    assert first != different
    assert len(first) == 16
    assert sum(bool(case["expect_valid"]) for case in first) == 14
    families = Counter(case["family"] for case in first)
    assert families["holdout_overlap_reassignment"] == 3
    assert families["holdout_capacity_reassignment"] == 3
    assert families["holdout_multi_need_reassignment"] == 3
    assert families["holdout_stock_safe_reassignment"] == 3
    features = Counter(feature for case in first for feature in case["features"])
    assert {
        "overlapping_zones",
        "capacity_greater_than_one",
        "multi_need",
        "inventory_shortage",
        "expiry_tie",
        "empty_queue",
        "high_cardinality",
        "malformed",
    } <= features.keys()


def test_opened_stock_scarcity_counterexample_is_exact_and_non_identifying() -> None:
    module = _load("quietrelay_v2_opened_cases", "scripts/quietrelay_v2_opened_cases.py")
    case = next(
        current
        for current in module.opened_cases()
        if current["family"] == "stock_scarcity_counterexample"
    )
    payload = case["payload"]
    assert len(payload["requests"]) == 2
    assert len(payload["stock"]) == 2
    assert len(payload["volunteers"]) == 1
    assert payload["requests"][0]["zone"] == payload["requests"][1]["zone"]
    assert payload["requests"][0]["urgency"] > payload["requests"][1]["urgency"]
    assert payload["requests"][0]["needs"][0]["item"] not in {
        lot["item"] for lot in payload["stock"]
    }
    assert payload["requests"][1]["needs"][0]["item"] in {
        lot["item"] for lot in payload["stock"]
    }
    assert set(payload) == {"today", "requests", "stock", "volunteers"}
