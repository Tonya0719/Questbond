from ..schemas.agent import WorkflowStatus


ALLOWED_TRANSITIONS = {
    WorkflowStatus.COLLECTING_INFORMATION: {WorkflowStatus.NEEDS_CLARIFICATION, WorkflowStatus.READY_FOR_SCHEDULING,
                                          WorkflowStatus.HUMAN_REVIEW_REQUIRED, WorkflowStatus.ERROR},
    WorkflowStatus.NEEDS_CLARIFICATION: {WorkflowStatus.COLLECTING_INFORMATION, WorkflowStatus.ERROR},
    WorkflowStatus.READY_FOR_SCHEDULING: {WorkflowStatus.ASSIGNMENT_IN_PROGRESS, WorkflowStatus.ERROR},
    WorkflowStatus.ASSIGNMENT_IN_PROGRESS: {WorkflowStatus.RECOMMENDATION_CREATED, WorkflowStatus.NO_FEASIBLE_ASSIGNMENT,
                                            WorkflowStatus.NEEDS_CLARIFICATION, WorkflowStatus.HUMAN_REVIEW_REQUIRED,
                                            WorkflowStatus.ERROR},
}


def ensure_transition(current: str, target: str) -> None:
    current_status, target_status = WorkflowStatus(current), WorkflowStatus(target)
    if target_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ValueError(f"Invalid workflow transition: {current_status.value} -> {target_status.value}")
