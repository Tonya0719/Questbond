from ..intake.mock_intake import MockIntake


class MockAgentClient:
    """Deterministic local substitute used by agent implementations and tests."""

    def __init__(self):
        self.extractor = MockIntake()

    def extract_request(self, raw_message: str) -> dict:
        return self.extractor.extract_request(raw_message)
