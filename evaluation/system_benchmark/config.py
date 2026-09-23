"""Paths, constants and the fixed synthetic world calendar for the benchmark.

All benchmark data is versioned and deterministic. Nothing here is read by the
product runtime; these are inputs to the benchmark harness only.
"""
from __future__ import annotations

from pathlib import Path

# evaluation/system_benchmark/
PACKAGE_DIR = Path(__file__).resolve().parent
# repository root
ROOT = PACKAGE_DIR.parents[1]

FIXTURES_DIR = PACKAGE_DIR / "fixtures" / "base"
GROUND_TRUTH_DIR = PACKAGE_DIR / "ground_truth"
CASES_CSV = PACKAGE_DIR / "cases.csv"
LIVE_SUBSET_CSV = PACKAGE_DIR / "live_subset.csv"

# Result artifacts live under results/system_benchmark/ (never overwrite other outputs).
RESULTS_DIR = ROOT / "results" / "system_benchmark"

# Fixed synthetic operational calendar. A weekday well clear of the product's
# 2025 seed data, so benchmark fixtures never collide with runtime data.
BENCHMARK_DATE = "2030-03-04"        # Monday
BENCHMARK_DATE_ALT = "2030-03-05"    # Tuesday (multi-day scenarios)

# Suites and their fixed offline case counts (total 120).
SUITE_TARGETS = {
    "request": 20,
    "scheduling": 25,
    "disruption": 30,
    "governance": 15,
    "agent": 15,
    "robustness": 15,
}
TOTAL_TARGET = sum(SUITE_TARGETS.values())

# Modular ground-truth files (robustness expectations are inlined/reused, by design).
GROUND_TRUTH_FILES = {
    "request": GROUND_TRUTH_DIR / "request_gt.csv",
    "scheduling": GROUND_TRUTH_DIR / "scheduling_gt.csv",
    "disruption": GROUND_TRUTH_DIR / "disruption_gt.csv",
    "governance": GROUND_TRUTH_DIR / "governance_gt.csv",
    "agent": GROUND_TRUTH_DIR / "agent_gt.csv",
}

# Per-case result CSV columns (shared across suites; suite-specific fields appended).
RESULT_COLUMNS = [
    "case_id", "suite", "scenario_type", "pass", "failure_reason",
    "expected", "actual", "duration_ms", "backend", "model",
    "input_tokens", "output_tokens", "cost_usd",
]

# Per-suite result file names under RESULTS_DIR.
RESULT_FILES = {
    "cases": "benchmark_cases.csv",
    "request": "request_results.csv",
    "scheduling": "scheduling_results.csv",
    "disruption": "disruption_results.csv",
    "governance": "governance_results.csv",
    "agent_live": "agent_live_results.csv",
    "robustness": "robustness_results.csv",
    "summary": "summary_metrics.json",
    "report": "evaluation_report.md",
}


def ensure_results_dir() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR
