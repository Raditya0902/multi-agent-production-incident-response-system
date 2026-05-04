from typing import TypedDict, List


class IncidentState(TypedDict):
    # Inputs
    raw_complaints: List[str]
    raw_logs: str

    # Correlation Agent output
    correlated_error: str
    affected_customers: List[str]

    # Severity Agent output
    severity: str         # "P0" | "P1" | "P2"
    severity_reason: str  # one-sentence justification

    # Root Cause Agent output
    root_cause: str
    relevant_files: List[str]
    rag_similarity_score: float  # top-1 ChromaDB cosine distance (0=identical, 2=opposite)

    # Fix Generator output
    code_patch: str
    patch_explanation: str

    # Execution Agent output
    test_results: str
    tests_passed: bool
    used_real_tests: bool  # True when validated against real repo test suite

    # Critic Agent output
    retry_count: int
    critic_feedback: str

    # Customer Response Agent output
    customer_replies: List[str]

    # Incident Report Agent output
    postmortem_report: str

    # Control
    escalate_to_human: bool
    status: str


def create_initial_state(complaints: List[str], logs: str) -> IncidentState:
    return IncidentState(
        raw_complaints=complaints,
        raw_logs=logs,
        correlated_error="",
        affected_customers=[],
        severity="",
        severity_reason="",
        root_cause="",
        relevant_files=[],
        rag_similarity_score=0.0,
        code_patch="",
        patch_explanation="",
        test_results="",
        tests_passed=False,
        used_real_tests=False,
        retry_count=0,
        critic_feedback="",
        customer_replies=[],
        postmortem_report="",
        escalate_to_human=False,
        status="started",
    )
