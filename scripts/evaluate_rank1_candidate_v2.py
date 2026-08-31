#!/usr/bin/env python3
"""Aggregate-only, fresh-process evaluator for QuietRelay v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from quietrelay_v2_holdout_cases import holdout_cases
from quietrelay_v2_opened_cases import opened_cases

from quietrelay.rank1_candidate_v2 import RecoverySessionV2, run_rank1_evidence_v2

EXPERIMENT_ID = "quietrelay-rank1-stock-aware-recovery-falsifier-v2"
OPENED_REQUIRED_FEATURES = frozenset(
    {
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
)
HOLDOUT_REQUIRED_FEATURES = frozenset(
    {
        "overlapping_zones",
        "capacity_greater_than_one",
        "multi_need",
        "inventory_shortage",
        "expiry_tie",
        "empty_queue",
        "high_cardinality",
        "malformed",
    }
)
OPENED_IMPROVEMENT_FAMILIES = frozenset(
    {
        "overlap_reassignment",
        "capacity_reassignment",
        "multi_need_reassignment",
        "stock_safe_reassignment",
    }
)
HOLDOUT_IMPROVEMENT_FAMILIES = frozenset(
    {
        "holdout_overlap_reassignment",
        "holdout_capacity_reassignment",
        "holdout_multi_need_reassignment",
        "holdout_stock_safe_reassignment",
    }
)


def _create_seed(path: Path) -> bytes:
    seed = os.urandom(32)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, seed)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return seed


def _read_seed(path: Path) -> bytes:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("holdout seed must be a regular mode-0600 file")
    seed = path.read_bytes()
    if len(seed) != 32:
        raise ValueError("holdout seed must contain exactly 32 bytes")
    return seed


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _run_direct(payload: str, option_id: str) -> dict[str, Any]:
    session = RecoverySessionV2(payload)
    session.inspect()
    session.select(option_id)
    evidence = json.loads(session.validate())
    evidence["plan"] = json.loads(session.authoritative_result())["plan"]
    return evidence


def _expected_option(payload: str) -> str:
    session = RecoverySessionV2(payload)
    options = json.loads(session.inspect())["options"]
    selected = min(
        options,
        key=lambda row: (
            -row["allocated_requests"],
            row["unresolved_decisions"],
            row["option_id"],
        ),
    )
    return str(selected["option_id"])


def _trace_valid(result: dict[str, Any]) -> bool:
    steps = result.get("audit", {}).get("steps", [])
    return [row.get("step") for row in steps] == [
        "inspect_conflicts",
        "select_recovery",
        "validate_recovery",
    ]


def _metrics_bucket() -> dict[str, int]:
    return {
        "cases": 0,
        "requests": 0,
        "control_allocated": 0,
        "candidate_allocated": 0,
        "control_unresolved": 0,
        "candidate_unresolved": 0,
        "strict_improvements": 0,
        "regressions": 0,
    }


def _family_output(
    buckets: dict[str, dict[str, int]], digests: dict[str, list[str]]
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for family, raw in sorted(buckets.items()):
        requests = raw["requests"]
        control_unresolved = raw["control_unresolved"]
        output[family] = {
            **raw,
            "control_coverage": raw["control_allocated"] / requests if requests else 1.0,
            "candidate_coverage": raw["candidate_allocated"] / requests if requests else 1.0,
            "coverage_gain": (
                (raw["candidate_allocated"] - raw["control_allocated"]) / requests
                if requests
                else 0.0
            ),
            "decision_reduction": (
                1 - raw["candidate_unresolved"] / control_unresolved
                if control_unresolved
                else 0.0
            ),
            "result_sha256": hashlib.sha256(
                "".join(sorted(digests[family])).encode()
            ).hexdigest(),
        }
    return output


def evaluate(
    cases: list[dict[str, Any]],
    *,
    mode: str,
    replay_label: str,
    seed_sha256: str | None,
) -> dict[str, Any]:
    started = time.monotonic()
    features: Counter[str] = Counter()
    valid_cases = 0
    rejected_cases = 0
    fail_closed_rejections = 0
    expectation_errors = 0
    live_model_errors = 0
    trace_failures = 0
    selection_errors = 0
    case_regressions = 0
    constraint_violations = 0
    external_action_violations = 0
    control_allocated = 0
    candidate_allocated = 0
    control_unresolved = 0
    candidate_unresolved = 0
    total_requests = 0
    case_digests: list[str] = []
    family_digests: defaultdict[str, list[str]] = defaultdict(list)
    family_buckets: defaultdict[str, dict[str, int]] = defaultdict(_metrics_bucket)

    for case_index, case in enumerate(cases):
        family = str(case["family"])
        features.update(str(feature) for feature in case["features"])
        payload = json.dumps(case["payload"], sort_keys=True, separators=(",", ":"))
        expected_valid = bool(case["expect_valid"])
        try:
            control = _run_direct(payload, "baseline")
        except (TypeError, ValueError, json.JSONDecodeError):
            rejected_cases += 1
            if expected_valid:
                expectation_errors += 1
            try:
                run_rank1_evidence_v2(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                fail_closed_rejections += 1
            else:
                expectation_errors += 1
            digest = hashlib.sha256(f"rejected:{family}:{case_index}".encode()).hexdigest()
            case_digests.append(digest)
            family_digests[family].append(digest)
            continue

        if not expected_valid:
            expectation_errors += 1
        valid_cases += 1
        request_count = len(case["payload"]["requests"])
        total_requests += request_count
        try:
            candidate = json.loads(run_rank1_evidence_v2(payload))
        except (RuntimeError, TimeoutError, TypeError, ValueError, json.JSONDecodeError, OSError):
            live_model_errors += 1
            digest = hashlib.sha256(f"live-error:{family}:{case_index}".encode()).hexdigest()
            case_digests.append(digest)
            family_digests[family].append(digest)
            continue

        expected_option = _expected_option(payload)
        if candidate.get("selected_option") != expected_option:
            selection_errors += 1
        if not _trace_valid(candidate):
            trace_failures += 1

        control_metrics = control["metrics"]
        candidate_metrics = candidate["metrics"]
        control_case_allocated = int(control_metrics["allocated_requests"])
        candidate_case_allocated = int(candidate_metrics["allocated_requests"])
        control_case_unresolved = int(control_metrics["unresolved_decisions"])
        candidate_case_unresolved = int(candidate_metrics["unresolved_decisions"])
        regression = (
            candidate_case_allocated < control_case_allocated
            or candidate_case_unresolved > control_case_unresolved
        )
        strict = (
            candidate_case_allocated > control_case_allocated
            and candidate_case_unresolved < control_case_unresolved
        )
        case_regressions += int(regression)
        constraint_violations += int(candidate_metrics["constraint_violations"])
        if candidate.get("external_actions") != [] or candidate_metrics["external_actions"] != []:
            external_action_violations += 1

        control_allocated += control_case_allocated
        candidate_allocated += candidate_case_allocated
        control_unresolved += control_case_unresolved
        candidate_unresolved += candidate_case_unresolved

        bucket = family_buckets[family]
        bucket["cases"] += 1
        bucket["requests"] += request_count
        bucket["control_allocated"] += control_case_allocated
        bucket["candidate_allocated"] += candidate_case_allocated
        bucket["control_unresolved"] += control_case_unresolved
        bucket["candidate_unresolved"] += candidate_case_unresolved
        bucket["strict_improvements"] += int(strict)
        bucket["regressions"] += int(regression)

        digest_input = {
            "family": family,
            "candidate": candidate,
            "control_metrics": control_metrics,
        }
        digest = hashlib.sha256(
            json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        case_digests.append(digest)
        family_digests[family].append(digest)

    feature_counts = dict(sorted(features.items()))
    required_features = OPENED_REQUIRED_FEATURES if mode == "opened" else HOLDOUT_REQUIRED_FEATURES
    improvement_families = (
        OPENED_IMPROVEMENT_FAMILIES if mode == "opened" else HOLDOUT_IMPROVEMENT_FAMILIES
    )
    family_metrics = _family_output(family_buckets, family_digests)
    missing_features = sorted(required_features - features.keys())
    missing_family_improvements = sorted(
        family
        for family in improvement_families
        if family not in family_metrics or family_metrics[family]["strict_improvements"] < 1
    )
    decision_reduction = (
        1 - candidate_unresolved / control_unresolved if control_unresolved else 0.0
    )
    control_coverage = control_allocated / total_requests if total_requests else 1.0
    candidate_coverage = candidate_allocated / total_requests if total_requests else 1.0
    coverage_gain = candidate_coverage - control_coverage
    aggregate_result_sha256 = hashlib.sha256(
        "".join(sorted(case_digests)).encode()
    ).hexdigest()
    comparison_payload = {
        "mode": mode,
        "seed_sha256": seed_sha256,
        "cases": len(cases),
        "valid_cases": valid_cases,
        "rejected_cases": rejected_cases,
        "fail_closed_rejections": fail_closed_rejections,
        "expectation_errors": expectation_errors,
        "live_model_errors": live_model_errors,
        "trace_failures": trace_failures,
        "selection_errors": selection_errors,
        "case_regressions": case_regressions,
        "constraint_violations": constraint_violations,
        "external_action_violations": external_action_violations,
        "control_allocated_requests": control_allocated,
        "candidate_allocated_requests": candidate_allocated,
        "control_unresolved_decisions": control_unresolved,
        "candidate_unresolved_decisions": candidate_unresolved,
        "total_requests": total_requests,
        "decision_reduction": decision_reduction,
        "control_allocation_coverage": control_coverage,
        "candidate_allocation_coverage": candidate_coverage,
        "allocation_coverage_gain": coverage_gain,
        "feature_counts": feature_counts,
        "missing_features": missing_features,
        "missing_family_improvements": missing_family_improvements,
        "family_metrics": family_metrics,
        "aggregate_result_sha256": aggregate_result_sha256,
    }
    comparison_sha256 = hashlib.sha256(
        json.dumps(comparison_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    elapsed = time.monotonic() - started
    passed = all(
        (
            valid_cases > 0,
            rejected_cases == fail_closed_rejections,
            expectation_errors == 0,
            live_model_errors == 0,
            trace_failures == 0,
            selection_errors == 0,
            case_regressions == 0,
            constraint_violations == 0,
            external_action_violations == 0,
            not missing_features,
            not missing_family_improvements,
            decision_reduction >= 0.30,
            coverage_gain >= 0.15,
            elapsed < 15 * 60,
        )
    )
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "mode": mode,
        "replay_label": replay_label,
        **comparison_payload,
        "comparison_sha256": comparison_sha256,
        "elapsed_seconds": elapsed,
        "cost_krw": 0,
        "gate_passed": passed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("opened", "holdout"), required=True)
    parser.add_argument("--replay-label", choices=("a", "b"), required=True)
    parser.add_argument("--seed-file", type=Path)
    parser.add_argument("--create-seed", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "opened":
        if args.seed_file is not None or args.create_seed:
            raise ValueError("opened mode cannot access a holdout seed")
        cases = opened_cases()
        seed_sha256 = None
    else:
        if args.seed_file is None:
            raise ValueError("holdout mode requires --seed-file")
        seed = _create_seed(args.seed_file) if args.create_seed else _read_seed(args.seed_file)
        cases = holdout_cases(seed)
        seed_sha256 = hashlib.sha256(seed).hexdigest()
    result = evaluate(
        cases,
        mode=args.mode,
        replay_label=args.replay_label,
        seed_sha256=seed_sha256,
    )
    _write_once(args.output, result)
    return 0 if result["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
