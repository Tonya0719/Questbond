from ..validators import parse_csv_set


def has_required_skills(technician, service_rule) -> bool:
    return parse_csv_set(service_rule["required_skills"]).issubset(parse_csv_set(technician["skills"]))


def has_required_certifications(technician, service_rule) -> bool:
    return parse_csv_set(service_rule["required_certifications"]).issubset(
        parse_csv_set(technician["certifications"])
    )


def eligibility_reasons(technician, service_rule) -> list[str]:
    reasons = []
    if technician["status"] != "AVAILABLE":
        reasons.append("STATUS_UNAVAILABLE")
    if not has_required_skills(technician, service_rule):
        reasons.append("SKILL_MISMATCH")
    if not has_required_certifications(technician, service_rule):
        reasons.append("CERTIFICATION_MISMATCH")
    return reasons
