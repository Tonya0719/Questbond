"""Coordinator explanations grounded in stored tool evidence, never free-form claims."""
REASONS = {
    "SKILL_MISMATCH": "does not have the required skills",
    "CERTIFICATION_MISMATCH": "does not have the required certification",
    "STATUS_UNAVAILABLE": "is unavailable",
    "WORKLOAD_LIMIT": "would exceed workload capacity",
    "NO_FEASIBLE_SLOT": "has no free slot within the customer window and working hours",
}


def candidate_dispositions(connection, trace):
    names = {row["technician_id"]: row["name_alias"] for row in connection.execute("SELECT * FROM technicians")}
    winner = trace.get("selected_candidate", {}).get("technician_id")
    rows = []
    for candidate in trace.get("eligible_candidates", []):
        tech = candidate["technician_id"]
        selected = tech == winner
        rows.append({"technician": names.get(tech, tech), "technician_id": tech,
            "disposition": "recommended" if selected else "lost tiebreak",
            "reason": ("Best deterministic rank" if selected else "Higher workload ratio or later feasible start; ID breaks exact ties"),
            "start": candidate["scheduled_start"], "workload_after": candidate["workload_after"],
            "workload_ratio": round(candidate["projected_workload_ratio"], 3)})
    request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (trace["request_id"],)).fetchone()
    for tech, reasons in trace.get("excluded_candidates", {}).items():
        reason = "; ".join(REASONS.get(item, item.replace("_", " ").lower()) for item in reasons)
        if "NO_FEASIBLE_SLOT" in reasons and request["window_start"] and request["window_end"]:
            bookings = connection.execute("""SELECT s.scheduled_start, s.scheduled_end FROM schedules s
                JOIN jobs j ON j.job_id=s.job_id WHERE s.technician_id=?
                AND s.assignment_status IN ('ASSIGNED','CONFIRMED') AND j.status IN ('SCHEDULED','IN_PROGRESS')
                AND s.scheduled_start < ? AND s.scheduled_end > ? ORDER BY s.scheduled_start""",
                (tech, request["window_end"], request["window_start"])).fetchall()
            if bookings:
                reason += "; existing visits: " + ", ".join(
                    f"{row['scheduled_start'][11:16]}–{row['scheduled_end'][11:16]}" for row in bookings)
        rows.append({"technician": names.get(tech, tech), "technician_id": tech,
                     "disposition": "excluded", "reason": reason, "start": None,
                     "workload_after": None, "workload_ratio": None})
    return rows


def explain_decision(connection, assignment, validation, trace, confirmed=False):
    if not validation.get("valid"):
        return "This recommendation failed validation: " + ", ".join(validation.get("violations", [])) + ". Coordinator review is required."
    if assignment["decision_status"] == "NEEDS_CLARIFICATION":
        return "More information is needed before a technician can be recommended."
    rows = candidate_dispositions(connection, trace)
    if assignment["decision_status"] == "NO_FEASIBLE_TECHNICIAN":
        intro = "No technician can complete this visit within the requested window. Coordinator review is required."
    else:
        name = next((row["technician"] for row in rows if row["disposition"] == "recommended"), assignment["technician_id"])
        intro = (f"{'Confirmed' if confirmed else 'Recommend'} {name} from {assignment['scheduled_start']} to {assignment['scheduled_end']}. "
                 f"Scheduled workload would increase from {assignment['workload_before']} to {assignment['workload_after']} minutes. "
                 "This is the best eligible rank by workload ratio, earliest start, then technician ID. "
                 + ("The appointment was confirmed by the coordinator." if confirmed else "The appointment awaits coordinator confirmation."))
    exclusions = [f"{row['technician']}: {row['reason']}." for row in rows if row["disposition"] != "recommended"]
    return intro + (" Other candidates: " + " ".join(exclusions) if exclusions else "")
