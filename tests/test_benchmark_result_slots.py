"""Offline benchmark runs must never overwrite paid live-run artifacts.

Fast regression tests: no suite is executed here, only the artifact-writing
contract (file slots + summary merging).
"""
from __future__ import annotations

import json

import pytest

from evaluation.system_benchmark import config, reporters


def test_agent_offline_and_live_use_distinct_files():
    offline_file = config.RESULT_FILES["agent_offline"]
    live_file = config.RESULT_FILES["agent_live"]
    assert offline_file != live_file
    assert live_file == "agent_live_results.csv"


def test_result_file_names_are_unique():
    names = list(config.RESULT_FILES.values())
    assert len(names) == len(set(names))


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    target = tmp_path / "system_benchmark"
    target.mkdir()
    monkeypatch.setattr(config, "RESULTS_DIR", target)
    return target


def _summary_path(results_dir):
    return results_dir / config.RESULT_FILES["summary"]


def test_merge_summary_creates_file_when_missing(results_dir):
    path = _summary_path(results_dir)
    assert not path.exists()

    reporters.merge_summary({"request": {"service_rule_accuracy": 1.0}})

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "request": {"service_rule_accuracy": 1.0}
    }


def test_merge_summary_preserves_existing_sections(results_dir):
    path = _summary_path(results_dir)
    path.write_text(
        json.dumps({
            "agent_live": {"task_completion_rate": 1.0, "latency_p50_ms": 29691},
            "request": {"service_rule_accuracy": 0.5},
        }),
        encoding="utf-8",
    )

    reporters.merge_summary({
        "request": {"service_rule_accuracy": 1.0},
        "agent_offline": {"tool_selection_accuracy": 1.0},
    })

    merged = json.loads(path.read_text(encoding="utf-8"))
    # Live section survives an offline merge, untouched.
    assert merged["agent_live"] == {"task_completion_rate": 1.0, "latency_p50_ms": 29691}
    # Offline sections are refreshed / added.
    assert merged["request"] == {"service_rule_accuracy": 1.0}
    assert merged["agent_offline"] == {"tool_selection_accuracy": 1.0}


def test_offline_write_sequence_does_not_touch_live_artifacts(results_dir):
    """Simulate the offline writes and assert the live artifacts are left alone."""
    live_csv = results_dir / config.RESULT_FILES["agent_live"]
    live_payload = "case_id,backend\nAGT001,gateway\n"
    live_csv.write_text(live_payload, encoding="utf-8")

    summary_path = _summary_path(results_dir)
    summary_path.write_text(
        json.dumps({"agent_live": {"task_completion_rate": 1.0}}), encoding="utf-8"
    )

    agent_rows = [{
        "case_id": "AGT001", "suite": "agent", "scenario_type": "routing",
        "pass": True, "failure_reason": "", "expected": "x", "actual": "x",
        "duration_ms": 8, "backend": "mock", "model": "mock",
    }]
    reporters.write_suite_results("agent_offline", agent_rows)
    reporters.merge_summary({"agent_offline": {"tool_selection_accuracy": 1.0}})

    # The paid live CSV is byte-identical.
    assert live_csv.read_text(encoding="utf-8") == live_payload
    # The offline CSV was created with the offline rows.
    offline_csv = results_dir / config.RESULT_FILES["agent_offline"]
    assert offline_csv.exists()
    assert "mock" in offline_csv.read_text(encoding="utf-8")
    # The live summary section is still present.
    merged = json.loads(summary_path.read_text(encoding="utf-8"))
    assert merged["agent_live"] == {"task_completion_rate": 1.0}
    assert merged["agent_offline"] == {"tool_selection_accuracy": 1.0}


def test_offline_run_writes_agent_offline_slot():
    """Guard the runner itself: offline() must not reference the live slot."""
    import inspect

    from evaluation.system_benchmark import run

    source = inspect.getsource(run.offline)
    assert 'write_suite_results("agent_offline", agent_rows)' in source
    assert '"agent_live"' not in source
    assert "reporters.merge_summary(summary)" in source
    assert "write_summary(" not in source
