import os
import pytest
from agents.state import IncidentState, create_initial_state


@pytest.fixture
def sample_logs() -> str:
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "sample_logs", "indexerror_log.txt",
    )
    with open(log_path) as f:
        return f.read()


@pytest.fixture
def sample_state(sample_logs) -> IncidentState:
    return create_initial_state(
        complaints=[
            "App crashes on upload — Alice",
            "Error every time I submit — Bob",
        ],
        logs=sample_logs,
    )


@pytest.fixture
def state_after_correlation(sample_state) -> IncidentState:
    state = dict(sample_state)
    state["correlated_error"] = "IndexError at data_processing.py:42 during file upload batch processing"
    state["affected_customers"] = ["Alice Johnson", "Bob Martinez"]
    return state
