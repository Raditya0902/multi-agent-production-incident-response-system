import os
import tempfile
import pytest

# Point the DB at a temp file so tests never touch the real incidents.db
@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test_incidents.db")
    monkeypatch.setenv("INCIDENT_DB_PATH", db_file)
    # Reset the module-level DB_PATH that was already imported
    import db.history as h
    monkeypatch.setattr(h, "DB_PATH", db_file)
    yield db_file


SAMPLE_STATE = {
    "status": "complete",
    "severity": "P1",
    "severity_reason": "Core feature broken for 2 users.",
    "correlated_error": "IndexError at data_processing.py:42",
    "root_cause": "Missing bounds check before list indexing.",
    "relevant_files": ["data_processing.py"],
    "code_patch": "===FILE===\ndata_processing.py\n===FIXED===\nreturn items[index] if index < len(items) else None",
    "patch_explanation": "Added bounds check.",
    "test_results": "4 passed in 0.01s",
    "tests_passed": True,
    "retry_count": 1,
    "affected_customers": ["Alice Johnson", "Bob Martinez"],
    "customer_replies": ["To: Alice Johnson\nDear Alice, issue resolved."],
    "postmortem_report": "# Incident Report\n## Summary\nFixed.",
    "escalate_to_human": False,
}


def test_save_and_retrieve():
    from db.history import save_incident, get_incident
    incident_id = save_incident(SAMPLE_STATE, run_time_seconds=18.5)
    assert incident_id == 1

    record = get_incident(incident_id)
    assert record is not None
    assert record["severity"] == "P1"
    assert record["severity_reason"] == "Core feature broken for 2 users."
    assert record["correlated_error"] == SAMPLE_STATE["correlated_error"]
    assert record["root_cause"] == SAMPLE_STATE["root_cause"]
    assert record["tests_passed"] is True
    assert record["affected_customers"] == ["Alice Johnson", "Bob Martinez"]
    assert record["relevant_files"] == ["data_processing.py"]
    assert record["run_time_seconds"] == 18.5


def test_list_incidents_newest_first():
    from db.history import save_incident, list_incidents
    save_incident(SAMPLE_STATE, 10.0)
    save_incident({**SAMPLE_STATE, "correlated_error": "Second incident"}, 20.0)

    rows = list_incidents()
    assert len(rows) == 2
    assert rows[0]["correlated_error"] == "Second incident"  # newest first
    assert rows[1]["correlated_error"] == SAMPLE_STATE["correlated_error"]


def test_delete_incident():
    from db.history import save_incident, get_incident, delete_incident
    incident_id = save_incident(SAMPLE_STATE, 5.0)
    assert get_incident(incident_id) is not None

    delete_incident(incident_id)
    assert get_incident(incident_id) is None


def test_delete_all():
    from db.history import save_incident, list_incidents, delete_all_incidents
    save_incident(SAMPLE_STATE, 5.0)
    save_incident(SAMPLE_STATE, 5.0)
    assert len(list_incidents()) == 2

    delete_all_incidents()
    assert list_incidents() == []


def test_get_nonexistent_returns_none():
    from db.history import get_incident
    assert get_incident(9999) is None


def test_escalated_state_saved_correctly():
    from db.history import save_incident, get_incident
    escalated = {**SAMPLE_STATE, "tests_passed": False, "escalate_to_human": True, "status": "escalated"}
    incident_id = save_incident(escalated, 45.0)
    record = get_incident(incident_id)
    assert record["tests_passed"] is False
    assert record["escalate_to_human"] is True
    assert record["status"] == "escalated"
