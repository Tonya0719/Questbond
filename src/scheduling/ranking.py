def rank_candidates(candidates):
    return sorted(candidates, key=lambda candidate: (
        candidate["projected_workload_ratio"], candidate["scheduled_start"], candidate["technician_id"]
    ))
