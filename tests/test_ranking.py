from src.scheduling.ranking import rank_candidates


def test_lexicographic_ranking_and_id_tie_break():
    candidates = [
        {"technician_id": "T002", "projected_workload_ratio": .5, "scheduled_start": "2025-01-15T10:00"},
        {"technician_id": "T001", "projected_workload_ratio": .5, "scheduled_start": "2025-01-15T10:00"},
        {"technician_id": "T003", "projected_workload_ratio": .25, "scheduled_start": "2025-01-15T12:00"},
    ]
    assert [c["technician_id"] for c in rank_candidates(candidates)] == ["T003", "T001", "T002"]
