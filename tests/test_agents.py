import os
import pytest

from agents.state import create_initial_state
from agents.execution_agent import (
    parse_code_patch,
    write_test_harness,
    run_in_subprocess,
)
from graph.workflow import route_after_execution


# ---------------------------------------------------------------------------
# Patch parser tests (no LLM, no network)
# ---------------------------------------------------------------------------

SAMPLE_PATCH = """===FILE===
data_processing.py
===ORIGINAL===
result = items[index]
===FIXED===
result = items[index] if index < len(items) else None
===EXPLANATION===
Added bounds check before list indexing to handle empty or undersized input lists."""


def test_parse_code_patch_file():
    parsed = parse_code_patch(SAMPLE_PATCH)
    assert parsed["file"] == "data_processing.py"


def test_parse_code_patch_original():
    parsed = parse_code_patch(SAMPLE_PATCH)
    assert "items[index]" in parsed["original"]


def test_parse_code_patch_fixed():
    parsed = parse_code_patch(SAMPLE_PATCH)
    assert "index < len(items)" in parsed["fixed"]


def test_parse_code_patch_explanation():
    parsed = parse_code_patch(SAMPLE_PATCH)
    assert "bounds check" in parsed["explanation"].lower()


# ---------------------------------------------------------------------------
# Router logic tests (no LLM, no network)
# ---------------------------------------------------------------------------

def test_route_passes_on_tests_passed(state_after_correlation):
    state = dict(state_after_correlation)
    state["tests_passed"] = True
    state["retry_count"] = 1
    assert route_after_execution(state) == "customer_response"


def test_route_retries_on_failure(state_after_correlation):
    state = dict(state_after_correlation)
    state["tests_passed"] = False
    state["retry_count"] = 1
    assert route_after_execution(state) == "critic"


def test_route_escalates_at_max_retries(state_after_correlation):
    state = dict(state_after_correlation)
    state["tests_passed"] = False
    state["retry_count"] = 3
    assert route_after_execution(state) == "escalate"


def test_route_escalates_beyond_max_retries(state_after_correlation):
    state = dict(state_after_correlation)
    state["tests_passed"] = False
    state["retry_count"] = 5
    assert route_after_execution(state) == "escalate"


# ---------------------------------------------------------------------------
# Execution agent tests (subprocess, no LLM, no network)
# ---------------------------------------------------------------------------

def test_execution_agent_indexerror_passes():
    """Subprocess runner: test harness for IndexError fix should pass."""
    patch = parse_code_patch(SAMPLE_PATCH)
    test_dir = write_test_harness(patch)
    try:
        output, passed = run_in_subprocess(test_dir)
        assert passed, f"Tests should pass with correct fix.\nOutput:\n{output}"
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


def test_execution_agent_keyerror_passes():
    key_patch = """===FILE===
payment_service.py
===ORIGINAL===
amount = payload["transaction"]["amount"]
===FIXED===
transaction = payload.get("transaction", {})
amount = transaction.get("amount") or payload.get("amount")
===EXPLANATION===
Use .get() for safe key access to handle missing 'transaction' key."""
    patch = parse_code_patch(key_patch)
    test_dir = write_test_harness(patch)
    try:
        output, passed = run_in_subprocess(test_dir)
        assert passed, f"Tests should pass.\nOutput:\n{output}"
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# RAG retrieval test (requires ingestion to have run)
# ---------------------------------------------------------------------------

def test_rag_retrieval_returns_results():
    from rag.vectorstore import retrieve_context, _get_collection
    collection = _get_collection()
    if collection.count() == 0:
        pytest.skip("ChromaDB not populated — run 'python -m rag.ingestion' first")
    results = retrieve_context("IndexError list index out of range", top_k=2)
    assert len(results) >= 1
    assert isinstance(results[0], str)
    assert len(results[0]) > 10


def test_rag_retrieval_is_relevant():
    from rag.vectorstore import retrieve_context, _get_collection
    collection = _get_collection()
    if collection.count() == 0:
        pytest.skip("ChromaDB not populated — run 'python -m rag.ingestion' first")
    results = retrieve_context("KeyError missing transaction key in payment payload", top_k=1)
    assert len(results) >= 1
    # Should retrieve the payment-related incident
    assert any(kw in results[0].lower() for kw in ["keyerror", "payment", "transaction", "key"])


# ---------------------------------------------------------------------------
# Initial state factory test
# ---------------------------------------------------------------------------

def test_severity_in_initial_state():
    state = create_initial_state(complaints=["test"], logs="test log")
    assert state["severity"] == ""
    assert state["severity_reason"] == ""


def test_create_initial_state_zero_fills():
    state = create_initial_state(complaints=["test"], logs="test log")
    assert state["retry_count"] == 0
    assert state["tests_passed"] is False
    assert state["escalate_to_human"] is False
    assert state["correlated_error"] == ""
    assert state["affected_customers"] == []
    assert state["customer_replies"] == []


# ---------------------------------------------------------------------------
# Full pipeline integration test (requires GROQ_API_KEY)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_full_pipeline_indexerror():
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY not set")

    log_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "sample_logs", "indexerror_log.txt",
    )
    with open(log_path) as f:
        logs = f.read()

    from graph.workflow import app
    state = create_initial_state(
        complaints=["App crashes on upload — Alice", "Error every time — Bob"],
        logs=logs,
    )
    result = app.invoke(state)

    assert result["status"] in ("complete", "escalated", "tests_passed", "tests_failed")
    assert result["correlated_error"] != ""
    assert result["root_cause"] != ""
    assert len(result["customer_replies"]) > 0 or result["escalate_to_human"]
    assert result["postmortem_report"] != ""
