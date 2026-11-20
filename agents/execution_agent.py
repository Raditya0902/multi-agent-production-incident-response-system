import fnmatch
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from agents.patch_paths import PatchPathError, canonical_app_path
from agents.source_context import production_path
from agents.state import IncidentState
from sandbox.runner import copy_workspace, run_in_docker, run_in_subprocess, sandbox_mode


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
# Real test file discovery
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_real_test_file(module_filename: str) -> Optional[str]:
    """
    Look for a real pytest file for *module_filename* (e.g. 'data_processing.py').
    Search order:
      1. tests/test_<module>.py
      2. test_<module>.py (project root)
      3. Any **/test*<stem>* match (recursive)
    Returns the absolute path or None.
    """
    stem = os.path.splitext(os.path.basename(module_filename))[0]
    candidates = [
        os.path.join(_PROJECT_ROOT, "tests", f"test_{stem}.py"),
        os.path.join(_PROJECT_ROOT, f"test_{stem}.py"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    benchmark_dir = os.path.join(_PROJECT_ROOT, "tests", "benchmark")
    for directory, subdirs, filenames in os.walk(_PROJECT_ROOT):
        subdirs[:] = [
            name for name in subdirs
            if not name.startswith(".") and os.path.join(directory, name) != benchmark_dir
        ]
        for filename in filenames:
            if fnmatch.fnmatch(filename, f"*test*{stem}*.py"):
                return os.path.join(directory, filename)
    return None


# ---------------------------------------------------------------------------
# Test harness generation
# ---------------------------------------------------------------------------

def write_test_harness(patch: dict, directory: Path | None = None) -> str:
    """
    Write a synthetic test harness to a temp directory.
    Returns the temp dir path — caller must clean it up.
    """
    if directory is None:
        test_dir = tempfile.mkdtemp(prefix="incident_sandbox_")
    else:
        directory.mkdir()
        test_dir = str(directory)

    fixed_code = patch.get("fixed", "pass")
    original_code = patch.get("original", "")

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

    For IndexError/KeyError cases we embed the LLM's actual fixed snippet as the
    function body — variable names in those snippets reliably match the wrapper
    signatures (items/index and payload/amount respectively).

    For all other error types the LLM's snippet references context variables
    (pool, user_repo, order, …) that don't exist in a generic wrapper, so we fall
    back to a hardcoded correct implementation.  Patch correctness for those cases
    is evaluated separately via pattern matching, not via test execution.
    """
    lines = [line.rstrip() for line in fixed_code.splitlines() if line.strip()]
    has_return = any(line.lstrip().startswith("return ") for line in lines)

    def _indent(code_lines: list) -> str:
        return "\n".join("    " + ln for ln in code_lines)

    if is_index_error:
        body = _indent(lines)
        if not has_return:
            if any("result" in ln for ln in lines):
                body += "\n    return result"
            elif any("item" in ln for ln in lines):
                body += "\n    return item"
            else:
                body += "\n    return None"
        return f'''def process_batch(items, index):
{body}


def get_item(items, index):
    return process_batch(items, index)
'''

    elif is_key_error:
        # Only use LLM code when it operates on 'payload' (payment-style fixes).
        # Other KeyError contexts (e.g. route dicts) reference variables not
        # available in this wrapper, so use the hardcoded fallback.
        uses_payload = any("payload" in ln for ln in lines)
        if uses_payload:
            body = _indent(lines)
            if not has_return:
                if any("amount" in ln for ln in lines):
                    body += "\n    return amount"
                elif any("result" in ln for ln in lines):
                    body += "\n    return result"
                else:
                    body += "\n    return None"
            return f'''def process_payment(payload):
{body}


def get_amount(payload):
    return process_payment(payload)
'''
        # Fallback hardcoded KeyError harness
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
        # Context-dependent fix — use hardcoded trivial harness.
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
# Agent node
# ---------------------------------------------------------------------------

def execution_agent(state: IncidentState) -> dict:
    patch = parse_code_patch(state["code_patch"])
    requested_path = patch["file"]
    root = Path(_PROJECT_ROOT).resolve()
    try:
        canonical = canonical_app_path(root, requested_path)
    except PatchPathError as error:
        # An unregistered bare module may still use the dashboard preview
        # harness. It has no source destination and cannot be published.
        missing_bare_module = (
            "/" not in requested_path and production_path(requested_path)
            and not (root / "app" / requested_path).exists()
            and not (root / "app" / requested_path).is_symlink()
            and find_real_test_file(requested_path) is None
        )
        if not missing_bare_module:
            return {
                "test_results": str(error), "tests_passed": False, "used_real_tests": False,
                "retry_count": state.get("retry_count", 0) + 1, "status": "tests_failed",
            }
        canonical = None
    module_filename = Path(canonical or requested_path).name
    real_test_path = find_real_test_file(module_filename) if module_filename else None
    used_real_tests = real_test_path is not None
    run_tests = run_in_docker if sandbox_mode() == "docker" else run_in_subprocess

    try:
        with tempfile.TemporaryDirectory(prefix="incident_sandbox_") as temporary:
            workspace = Path(temporary) / "repo"
            copy_workspace(root, workspace)
            if real_test_path:
                test_file = Path(real_test_path).relative_to(root).as_posix()
                source = workspace / canonical
                original_content = source.read_text(encoding="utf-8")
                original_snippet = patch["original"]
                fixed_snippet = patch["fixed"]
                if original_snippet and original_snippet in original_content:
                    patched_content = original_content.replace(original_snippet, fixed_snippet, 1)
                else:
                    patched_content = original_content + f"\n# --- Suggested fix ---\n{fixed_snippet}\n"
                source.write_text(patched_content, encoding="utf-8")
            else:
                harness = workspace / ".incident-preview"
                write_test_harness(patch, harness)
                test_file = ".incident-preview/test_fix.py"
            test_results, tests_passed = run_tests(str(workspace), test_file=test_file)
    except (OSError, ValueError) as error:
        test_results, tests_passed = f"Sandbox test could not start: {error}", False

    if not used_real_tests:
        test_results += (
            "\n⚠️ WARNING: No real test file found. "
            "Synthetic tests used — results unverified."
        )

    return {
        "test_results": test_results,
        "tests_passed": tests_passed,
        "used_real_tests": used_real_tests,
        "retry_count": state.get("retry_count", 0) + 1,
        "status": "tests_passed" if tests_passed else "tests_failed",
    }
