"""Compatibility exports for application data models."""
from .schemas.assignment import AssignmentResult, Candidate
from .schemas.request import StructuredRequest

__all__ = ["AssignmentResult", "Candidate", "StructuredRequest"]
