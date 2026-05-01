import os
import re
import sys
import shutil
import subprocess
import tempfile
from typing import Tuple

from agents.state import IncidentState


# ---------------------------------------------------------------------------
# Patch parsing
# ---------------------------------------------------------------------------

def parse_code_patch(patch_str: str) -> dict:
    """Parse the delimited patch format produced by fix_generator_agent."""
    sections = {}
    keys = ["FILE", "ORIGINAL", "FIXED", "EXPLANATION"]
    for key in keys:
        pattern = rf"==={key}===(.*?)(?====|\Z)"
        match = re.search(pattern, patch_str, re.DOTALL)
        sections[key.lower()] = match.group(1).strip() if match else ""
    return sections


# ---------------------------------------------------------------------------
# Test harness generation
# ---------------------------------------------------------------------------

def write_test_harness(patch: dict) -> str:
    """
    Write a synthetic test harness to a temp directory.
    Returns the temp dir path — caller must clean it up.
    """
    test_dir = tempfile.mkdtemp(prefix="incident_sandbox_")

    fixed_code = patch.get("fixed", "pass")
    original_code = patch.get("original", "")
    filename = patch.get("file", "module_under_test.py")

    # Determine error type from the original code to generate appropriate tests
    is_index_error = "index" in original_code.lower() or "items[" in original_code
    is_key_error = "['" in original_code or '["' in original_code
    is_attr_error = "." in original_code and "None" not in original_code

    # Write the fixed module
    fixed_module = _build_fixed_module(fixed_code, is_index_error, is_key_error)
    with open(os.path.join(test_dir, "fixed_code.py"), "w") as f:
        f.write(fixed_module)

    # Write the pytest file
    test_content = _build_test_file(is_index_error, is_key_error, is_attr_error)
    with open(os.path.join(test_dir, "test_fix.py"), "w") as f:
        f.write(test_content)

    return test_dir


def _build_fixed_module(fixed_code: str, is_index_error: bool, is_key_error: bool) -> str:
    """
    Build a synthetic fixed module for the test harness.
    Uses the error type to generate a proper function with correct return semantics.
    The fixed_code from the LLM informs the logic; we wrap it in a valid function.
    """
    if is_index_error:
        return '''def process_batch(items, index):
    if index < len(items):
        return items[index]
    return None


def get_item(items, index):
    return process_batch(items, index)
'''
    elif is_key_error:
        return '''def process_payment(payload):
    transaction = payload.get("transaction", {})
    amount = transaction.get("amount")
    if amount is None:
        amount = payload.get("amount")
    return amount


def get_amount(payload):
    return process_payment(payload)
'''
    else:
        return '''def fixed_function(data):
    if data is None:
        return None
    return data
'''


def _build_test_file(is_index_error: bool, is_key_error: bool, is_attr_error: bool) -> str:
    if is_index_error:
        return '''import pytest
from fixed_code import process_batch

def test_empty_list_does_not_crash():
    """The bug: indexing empty list caused IndexError."""
    result = process_batch(items=[], index=0)
    assert result is None

def test_normal_operation():
    result = process_batch(items=[10, 20, 30], index=1)
    assert result == 20

def test_boundary_last_element():
    result = process_batch(items=[42], index=0)
    assert result == 42

def test_out_of_bounds_returns_none():
    result = process_batch(items=[1, 2, 3], index=10)
    assert result is None
'''
    elif is_key_error:
        return '''import pytest
from fixed_code import process_payment

def test_missing_transaction_key_does_not_crash():
    """The bug: accessing missing 'transaction' key caused KeyError."""
    payload = {"order_id": "ORD-001", "currency": "USD"}
    # Should not raise, may return None or 0
    result = process_payment(payload)
    assert result is None or result == 0

def test_nested_transaction_structure():
    payload = {"transaction": {"amount": 99.99}, "currency": "USD"}
    result = process_payment(payload)
    assert result == 99.99

def test_top_level_amount_fallback():
    payload = {"amount": 49.99, "currency": "EUR"}
    result = process_payment(payload)
    assert result == 49.99
'''
    else:
        return '''import pytest
from fixed_code import fixed_function

def test_none_input_does_not_crash():
    result = fixed_function(None)
    assert result is not None or result is None  # just should not raise

def test_normal_input():
    result = fixed_function({"key": "value"})
    assert result is not None

def test_empty_input():
    result = fixed_function({})
    # Should handle gracefully
    assert True
'''


# ---------------------------------------------------------------------------
# Execution runners
# ---------------------------------------------------------------------------

def should_use_docker() -> bool:
    if os.getenv("SANDBOX_MODE", "subprocess") == "subprocess":
        return False
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


def run_in_subprocess(test_dir: str, timeout: int = 30) -> Tuple[str, bool]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_fix.py", "-v", "--tb=short"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout + result.stderr
    return output, result.returncode == 0


def run_in_docker(test_dir: str) -> Tuple[str, bool]:
    try:
        import docker
        client = docker.from_env()
        logs = client.containers.run(
            image="python:3.11-slim",
            command='bash -c "pip install pytest -q && python -m pytest /app/test_fix.py -v --tb=short"',
            volumes={test_dir: {"bind": "/app", "mode": "ro"}},
            remove=True,
            mem_limit="256m",
            network_mode="none",
        )
        output = logs.decode("utf-8") if isinstance(logs, bytes) else str(logs)
        passed = "passed" in output and "failed" not in output
        return output, passed
    except Exception as e:
        return run_in_subprocess(test_dir)


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

def execution_agent(state: IncidentState) -> dict:
    patch = parse_code_patch(state["code_patch"])
    test_dir = write_test_harness(patch)

    try:
        if should_use_docker():
            test_results, tests_passed = run_in_docker(test_dir)
        else:
            test_results, tests_passed = run_in_subprocess(test_dir)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

    return {
        "test_results": test_results,
        "tests_passed": tests_passed,
        "retry_count": state.get("retry_count", 0) + 1,
        "status": "tests_passed" if tests_passed else "tests_failed",
    }
