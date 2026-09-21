"""Conservative business checks, independent of model urgency/confidence claims."""
import json
import re

HAZARDS = {
    "active flooding": r"\b(?:flooding|water is flooding|flooded)\b",
    "electrical sparks": r"\b(?:sparking|sparks|exposed live wire)\b",
    "possible gas leak": r"\b(?:smell (?:of )?gas|gas leak|gas smell)\b",
}
ISSUES = {
    "plumbing": r"\b(?:pipe|tap|toilet|drain|sink)\b",
    "air-conditioning": r"\b(?:aircon|air conditioner|air-conditioning|ac)\b",
    "electrical": r"\b(?:socket|power trip|light repair|sparking|sparks)\b",
    "painting": r"\b(?:paint|painting|repaint|wall touch-up)\b",
    "carpentry": r"\b(?:carpentry|door frame|door repair|cabinet)\b",
    "masonry": r"\b(?:cement|masonry|wall crack|tile repair)\b",
}


def assess_request(text):
    hazards = []
    for label, pattern in HAZARDS.items():
        for match in re.finditer(pattern, text, re.I):
            prefix = text[max(0, match.start() - 20):match.start()].lower()
            if not re.search(r"\b(?:not|no|without)\s+(?:any\s+)?$", prefix):
                hazards.append(label)
                break
    issues = [category for category, pattern in ISSUES.items() if re.search(pattern, text, re.I)]
    mixed = len(issues) > 1 and bool(re.search(r"\b(?:and|also)\b|&", text, re.I))
    return {"hazard_flags": hazards, "injection_flag": bool(re.search(
        r"ignore (?:previous|prior|all) instructions|regardless of availability|bypass (?:approval|rules)", text, re.I)),
        "issue_categories": issues, "human_review_required": bool(hazards or mixed)}


def get_triage(connection, request_id):
    raw = connection.execute("SELECT raw_message FROM customer_requests WHERE request_id=?", (request_id,)).fetchone()
    if not raw:
        raise ValueError("Unknown request.")
    result = assess_request(raw["raw_message"])
    connection.execute("INSERT OR REPLACE INTO request_triage VALUES (?,?,?,?,?)", (
        request_id, json.dumps(result["hazard_flags"]), int(result["injection_flag"]),
        json.dumps(result["issue_categories"]), int(result["human_review_required"])))
    connection.commit()
    return result
