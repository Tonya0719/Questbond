"""Write benchmark result artifacts and print a terminal summary.

Every displayed number is computed from the per-case result rows. Nothing is
prefilled. Missing values (e.g. live cost) stay missing, never zero.
"""
from __future__ import annotations

import csv
import json
from datetime import date

from . import BENCHMARK_VERSION, config


def _fmt_pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def write_case_registry(cases: list[dict]) -> None:
    path = config.RESULTS_DIR / config.RESULT_FILES["cases"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0].keys()))
        writer.writeheader()
        writer.writerows(cases)


def write_suite_results(suite_key: str, rows: list[dict]) -> None:
    path = config.RESULTS_DIR / config.RESULT_FILES[suite_key]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=config.RESULT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in config.RESULT_COLUMNS})


def write_summary(summary: dict) -> None:
    path = config.RESULTS_DIR / config.RESULT_FILES["summary"]
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def merge_summary(new_section: dict) -> None:
    """Merge live metrics into the existing summary without discarding offline metrics."""
    path = config.RESULTS_DIR / config.RESULT_FILES["summary"]
    existing = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.update(new_section)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def print_live_summary(live: dict, output_path) -> None:
    def pct(v):
        return "n/a" if v is None else f"{v * 100:.1f}%"

    def num(v, suffix=""):
        return "n/a" if v is None else f"{v:.0f}{suffix}"

    print("")
    print("Live Agent")
    print(f"  Task completion:                    {pct(live['task_completion_rate'])}")
    print(f"  Handoff accuracy:                   {pct(live['handoff_accuracy'])}")
    print(f"  Final-state accuracy:               {pct(live['final_state_accuracy'])}")
    print(f"  p50 latency:                        {num(live['latency_p50_ms'], ' ms')}")
    print(f"  p95 latency:                        {num(live['latency_p95_ms'], ' ms')}")
    print(f"  Avg input tokens:                   {num(live['average_input_tokens'])}")
    print(f"  Avg output tokens:                  {num(live['average_output_tokens'])}")
    cost = live["average_cost_per_completed_task_usd"]
    if cost is None:
        print(f"  Cost/completed task:                unavailable (provider cost not reported)")
    else:
        print(f"  Cost/completed task:                ${cost:.4f} "
              f"(over {live['priced_task_count']}/{live['completed_task_count']} priced tasks)")
    print("")
    print(f"Results:\n  {output_path}")


def _failed_cases(rows: list[dict]) -> list[str]:
    return [f"{r['case_id']} ({r['scenario_type']}): {r['failure_reason']}" for r in rows if not r["pass"]]


def write_report(summary: dict, all_rows: dict[str, list[dict]], mode: str) -> None:
    lines = [
        f"# Questbond System Benchmark Report",
        "",
        f"- Benchmark version: {BENCHMARK_VERSION}",
        f"- Date: {date.today().isoformat()}",
        f"- Mode: {mode}",
        f"- Backend: mock (offline deterministic)" if mode == "offline" else f"- Mode: {mode}",
        "",
        "## Case counts",
        "",
    ]
    total = 0
    for suite, rows in all_rows.items():
        passed = sum(1 for r in rows if r["pass"])
        total += len(rows)
        lines.append(f"- {suite}: {passed}/{len(rows)} passed")
    lines.append(f"- **total: {total} cases**")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Failed cases")
    lines.append("")
    any_failed = False
    for suite, rows in all_rows.items():
        failures = _failed_cases(rows)
        if failures:
            any_failed = True
            lines.append(f"### {suite}")
            lines.extend(f"- {item}" for item in failures)
            lines.append("")
    if not any_failed:
        lines.append("None — all cases passed.")
        lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.extend([
        "- Offline/mock results measure deterministic correctness and safety, not live Agent language quality.",
        "- Deterministic scheduling/recovery metrics are produced by Python, not the LLM.",
        "- Live latency/tokens/cost are collected only in `--mode live` (separate artifacts).",
        "- Multimodal visual accuracy is a separate evaluation track and is not included here.",
    ])
    lines.append("")
    path = config.RESULTS_DIR / config.RESULT_FILES["report"]
    path.write_text("\n".join(lines), encoding="utf-8")


def print_offline_summary(summary: dict, all_rows: dict[str, list[dict]]) -> None:
    total = sum(len(rows) for rows in all_rows.values())
    req, sch = summary["request"], summary["scheduling"]
    dsp, gov, rob = summary["disruption"], summary["governance"], summary["robustness"]
    print("")
    print("Questbond System Benchmark")
    print("")
    print(f"Offline cases: {total}")
    print("")
    print("Request")
    print(f"  Service-rule accuracy:              {_fmt_pct(req['service_rule_accuracy'])}")
    print(f"  Readiness accuracy:                 {_fmt_pct(req['readiness_accuracy'])}")
    print(f"  Clarification accuracy:             {_fmt_pct(req['clarification_accuracy'])}")
    print(f"  Fabrication rate:                   {_fmt_pct(req['fabrication_rate'])}")
    print("")
    print("Scheduling")
    print(f"  Feasible schedule rate:             {_fmt_pct(sch['schedule_feasibility_rate'])}")
    print(f"  Deterministic assignment agreement: {_fmt_pct(sch['deterministic_assignment_agreement'])}")
    print("")
    print("Disruption")
    print(f"  Affected-job precision:             {_fmt_pct(dsp['affected_job_precision'])}")
    print(f"  Affected-job recall:                {_fmt_pct(dsp['affected_job_recall'])}")
    print(f"  Unnecessary-change rate:            {_fmt_pct(dsp['unnecessary_change_rate'])}")
    print(f"  Recovery success rate:              {_fmt_pct(dsp['recovery_success_rate'])}")
    print("")
    print("Governance")
    print(f"  Pre-approval mutations:             {gov['pre_approval_mutation_count']}")
    print(f"  Rejected-plan mutations:            {gov['rejected_plan_mutation_count']}")
    print(f"  Unauthorized schedule mutations:    {gov['unauthorized_schedule_mutation_count']}")
    print("")
    print("Robustness")
    print(f"  Safe-failure rate:                  {_fmt_pct(rob['safe_failure_rate'])}")
    print("")
    print(f"Results:")
    print(f"  {config.RESULTS_DIR / config.RESULT_FILES['report']}")
