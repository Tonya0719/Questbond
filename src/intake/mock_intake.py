import re


class MockIntake:
    RULES = {
        "routine servicing": "AC-ROUTINE", "not cooling": "AC-DIAG", "aircon is leaking": "AC-LEAK",
        "aircon leak": "AC-LEAK", "tap leakage": "PL-LEAK", "pipe leak": "PL-LEAK",
        "drain blockage": "PL-BLOCK", "toilet blockage": "PL-BLOCK", "fixture replacement": "PL-FIXTURE",
        "socket repair": "EL-REPAIR", "light repair": "EL-REPAIR", "power trip": "EL-TRIP",
        "minor installation": "EL-INSTALL",
    }
    ZONES = ("North", "South", "East", "West", "Central")

    def extract_request(self, raw_message: str) -> dict:
        lowered = raw_message.lower()
        rule = next((value for phrase, value in self.RULES.items() if phrase in lowered), None)
        zone = next((zone for zone in self.ZONES if zone.lower() in lowered), None)
        dates = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", raw_message)
        return {"service_rule_id": rule, "zone": zone,
                "urgency": "URGENT" if "urgent" in lowered else "NORMAL",
                "window_start": dates[0] if len(dates) > 0 else None,
                "window_end": dates[1] if len(dates) > 1 else None}
