"""Questbond system benchmark runner.

Modes:
  validate  — check registry/GT/fixture integrity (no scoring).
  offline   — run deterministic offline suites (implemented in Checkpoint B2).
  live      — run the live Agent subset (implemented in Checkpoint B4).

Usage:
  python -m evaluation.system_benchmark.run --mode validate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script or module.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.system_benchmark import BENCHMARK_VERSION, config, loaders, metrics, reporters
from evaluation.system_benchmark.suites import (
    agent_suite,
    disruption_suite,
    governance_suite,
    request_suite,
    robustness_suite,
    scheduling_suite,
)

# Suites whose expectations live in modular GT files. Robustness is inlined by design.
_GT_BACKED_SUITES = {"request", "scheduling", "disruption", "governance", "agent"}
_INLINE_ROBUSTNESS_EXPECTED = {
    "safe_failure", "human_review", "idempotent", "scope_block",
}


def validate() -> int:
    errors: list[str] = []
    cases = loaders.load_cases()
    truth = loaders.load_ground_truth()

    # 1. Unique case IDs.
    ids = [c["case_id"] for c in cases]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        errors.append(f"Duplicate case IDs: {', '.join(duplicates)}")

    # 2. Every case maps to matching ground truth (or valid inline robustness expectation).
    for case in cases:
        suite, case_id, expected_ref = case["suite"], case["case_id"], case["expected_ref"]
        if suite == "robustness":
            # Robustness reuses another suite's mechanism OR an inline outcome token.
            reused = any(expected_ref in truth[s] for s in _GT_BACKED_SUITES)
            if expected_ref not in _INLINE_ROBUSTNESS_EXPECTED and not reused:
                errors.append(f"{case_id}: robustness expected_ref '{expected_ref}' is neither inline nor a known GT case")
            continue
        if suite not in _GT_BACKED_SUITES:
            errors.append(f"{case_id}: unknown suite '{suite}'")
            continue
        if expected_ref not in truth[suite]:
            errors.append(f"{case_id}: no {suite} ground truth for expected_ref '{expected_ref}'")

    # 3. Suite counts match the fixed targets.
    for suite, target in config.SUITE_TARGETS.items():
        count = sum(1 for c in cases if c["suite"] == suite)
        if count != target:
            errors.append(f"Suite '{suite}': expected {target} cases, found {count}")
    if len(cases) != config.TOTAL_TARGET:
        errors.append(f"Total cases: expected {config.TOTAL_TARGET}, found {len(cases)}")

    # 4. Fixture foreign-key integrity: seed the world and run integrity check.
    connection = loaders.new_world()
    try:
        fk_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            errors.append(f"Fixture foreign-key violations: {fk_violations}")
        # Every scheduled job/technician/customer/service_rule must resolve.
        orphan_sched = connection.execute(
            "SELECT COUNT(*) FROM schedules s LEFT JOIN jobs j ON j.job_id=s.job_id WHERE j.job_id IS NULL"
        ).fetchone()[0]
        if orphan_sched:
            errors.append(f"{orphan_sched} schedule rows reference missing jobs")
        orphan_job_rule = connection.execute(
            "SELECT COUNT(*) FROM jobs j LEFT JOIN service_rules r ON r.service_rule_id=j.service_rule_id WHERE r.service_rule_id IS NULL"
        ).fetchone()[0]
        if orphan_job_rule:
            errors.append(f"{orphan_job_rule} jobs reference missing service rules")
        counts = {
            "technicians": connection.execute("SELECT COUNT(*) FROM technicians").fetchone()[0],
            "customers": connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "jobs": connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "schedules": connection.execute("SELECT COUNT(*) FROM schedules").fetchone()[0],
            "service_rules": connection.execute("SELECT COUNT(*) FROM service_rules").fetchone()[0],
        }
    finally:
        connection.close()

    print(f"Questbond System Benchmark — validate (v{BENCHMARK_VERSION})")
    print(f"Fixtures: {counts}")
    print(f"Expected total cases: {config.TOTAL_TARGET}")
    for suite, target in config.SUITE_TARGETS.items():
        print(f"  {suite}: {target}")
    if errors:
        print("\nVALIDATION FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("\nVALIDATION PASSED: unique IDs, matching ground truth, valid fixtures.")
    print("Note: benchmark ground truth is loaded only for comparison; it is never read by runtime decision logic.")
    return 0


def offline() -> int:
    config.ensure_results_dir()
    cases = loaders.load_cases()
    truth = loaders.load_ground_truth()

    request_rows = request_suite.run(cases, truth)
    scheduling_rows = scheduling_suite.run(cases, truth)
    disruption_rows = disruption_suite.run(cases, truth)
    governance_rows = governance_suite.run(cases, truth)
    agent_rows = agent_suite.run(cases, truth)
    robustness_rows = robustness_suite.run(cases, truth)

    all_rows = {
        "request": request_rows, "scheduling": scheduling_rows, "disruption": disruption_rows,
        "governance": governance_rows, "agent": agent_rows, "robustness": robustness_rows,
    }

    summary = {
        "request": metrics.request_metrics(request_rows),
        "scheduling": metrics.scheduling_metrics(scheduling_rows),
        "disruption": metrics.disruption_metrics(disruption_rows),
        "governance": metrics.governance_metrics(governance_rows),
        "agent_offline": metrics.agent_offline_metrics(agent_rows),
        "robustness": metrics.robustness_metrics(robustness_rows),
    }

    reporters.write_case_registry(cases)
    reporters.write_suite_results("request", request_rows)
    reporters.write_suite_results("scheduling", scheduling_rows)
    reporters.write_suite_results("disruption", disruption_rows)
    reporters.write_suite_results("governance", governance_rows)
    reporters.write_suite_results("robustness", robustness_rows)
    # Offline artifacts stay strictly separate from live artifacts: an offline (mock)
    # run must NEVER write the agent_live slot, which holds paid live-run results.
    reporters.write_suite_results("agent_offline", agent_rows)
    # Merge instead of overwrite, so an offline run only refreshes its own sections
    # and leaves the `agent_live` section written by a live run intact.
    reporters.merge_summary(summary)
    reporters.write_report(summary, all_rows, mode="offline")
    reporters.print_offline_summary(summary, all_rows)

    total_failed = sum(1 for rows in all_rows.values() for r in rows if not r["pass"])
    print(f"\nFailed cases: {total_failed} / {sum(len(r) for r in all_rows.values())}")
    return 0


def live(approved: bool) -> int:
    from evaluation.system_benchmark.suites import live_runner
    from src.config import settings

    subset = loaders.load_live_subset()
    if not subset:
        print("No live_subset.csv found or it is empty.")
        return 1
    truth = loaders.load_ground_truth()
    est = live_runner.estimate(subset)

    output_path = config.RESULTS_DIR / config.RESULT_FILES["agent_live"]
    print("Live Agent benchmark — pre-run report")
    print(f"  Cases:            {est['cases']}")
    print(f"  Backend:          {est['backend']}")
    print(f"  Model:            {est['model']}")
    print(f"  Estimated calls:  ~{est['estimated_calls_avg']} (upper bound {est['estimated_calls_max']})")
    print(f"  Known cost:       provider-reported per call; missing stays missing")
    print(f"  Output path:      {output_path}")

    if settings.llm_backend == "mock":
        print("\nRefusing to run: LLM_BACKEND is 'mock'. Configure a live backend for a live run.")
        return 2
    if not approved:
        print("\nThis is a PAID live run. Re-run with --yes to execute after reviewing the report above.")
        return 0

    config.ensure_results_dir()
    rows = live_runner.run(subset, truth)
    summary = {"agent_live": metrics.agent_live_metrics(rows)}

    reporters.write_suite_results("agent_live", rows)
    # Merge live metrics into the summary file without discarding offline metrics.
    reporters.merge_summary(summary)
    reporters.print_live_summary(summary["agent_live"], output_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Questbond system benchmark")
    parser.add_argument("--mode", required=True, choices=["validate", "offline", "live"])
    parser.add_argument("--yes", action="store_true",
                        help="Explicit approval to execute a PAID live run (mode=live only).")
    args = parser.parse_args()
    if args.mode == "live":
        return live(args.yes)
    return {"validate": validate, "offline": offline}[args.mode]()


if __name__ == "__main__":
    raise SystemExit(main())
