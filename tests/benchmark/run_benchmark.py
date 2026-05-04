"""
Benchmark runner — evaluates the full pipeline against all 7 test cases.

Usage:
    python -m tests.benchmark.run_benchmark
    python -m tests.benchmark.run_benchmark --save-history
    python -m tests.benchmark.run_benchmark --max 3   # run only first N cases

Outputs:
    Printed table + tests/benchmark/results/latest.json
    With --save-history: also appends to tests/benchmark/results/history.jsonl
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.state import create_initial_state
from graph.workflow import app as pipeline_app
from tests.benchmark.ground_truth import GROUND_TRUTH

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# ---------------------------------------------------------------------------
# Test case definitions (drawn from test_cases.txt)
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": 1,
        "name": "IndexError — file upload crash",
        "target_file": "data_processing.py",
        "logs": (
            "2024-11-15 14:32:01 ERROR [data_processing] Unhandled exception in process_batch\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/data_processing.py\", line 42, in process_batch\n"
            "    result = items[index]\n"
            "IndexError: list index out of range\n"
            "Batch Size: 0"
        ),
        "complaints": [
            "Your app keeps crashing when I upload my CSV file!",
            "Getting an error every time I submit my data.",
            "App is completely broken for file uploads. Please fix ASAP!",
        ],
    },
    {
        "id": 2,
        "name": "KeyError — payment failure",
        "target_file": "payment_service.py",
        "logs": (
            "2024-11-16 09:15:44 ERROR [payment_service] Payment processing failure\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/payment_service.py\", line 87, in process_payment\n"
            '    amount = payload["transaction"]["amount"]\n'
            "KeyError: 'transaction'"
        ),
        "complaints": [
            "Payment keeps failing. I was charged but my order was never placed.",
            "Tried to checkout 4 times and keep getting an error.",
        ],
    },
    {
        "id": 3,
        "name": "TimeoutError — DB pool exhausted",
        "target_file": "database_service.py",
        "logs": (
            "2024-11-17 16:45:22 ERROR [database_service] Query timeout exceeded\n"
            "sqlalchemy.exc.TimeoutError: Connection pool timeout after 30s\n"
            "  File \"/app/database_service.py\", line 134, in execute_query\n"
            "    result = session.execute(query)\n"
            "Connection pool size: 5/5 (exhausted)\n"
            "Queue depth: 23 pending requests"
        ),
        "complaints": [
            "The app is extremely slow. Pages are taking over 30 seconds to load.",
        ],
    },
    {
        "id": 4,
        "name": "AttributeError — NoneType on user",
        "target_file": "notification_service.py",
        "logs": (
            "2024-11-18 11:04:33 ERROR [notification_service] Failed to send notification\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/notification_service.py\", line 78, in send_welcome_email\n"
            "    recipient = user_repo.find_by_id(user_id).email\n"
            "AttributeError: 'NoneType' object has no attribute 'email'"
        ),
        "complaints": [
            "I signed up but never received a welcome email. Can you resend it?",
        ],
    },
    {
        "id": 5,
        "name": "Mass outage — api_gateway KeyError",
        "target_file": "api_gateway.py",
        "logs": (
            "2024-11-19 08:00:01 ERROR [api_gateway] Service unavailable\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/api_gateway.py\", line 23, in route_request\n"
            "    response = service_registry[service_name]\n"
            "KeyError: 'user-service'\n"
            "Total failed requests in last 60s: 312"
        ),
        "complaints": [
            "I can't log in at all. Getting a server error immediately.",
            "Nothing works. Login, checkout, everything is down.",
            "Your entire site is broken right now.",
            "We can't access the platform. Our whole team is blocked.",
            "Nothing is loading. Is there an outage?",
        ],
    },
    {
        "id": 6,
        "name": "ZeroDivisionError — analytics",
        "target_file": "analytics_service.py",
        "logs": (
            "2024-11-20 15:22:10 ERROR [analytics_service] Report generation failed\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/analytics_service.py\", line 91, in compute_conversion_rate\n"
            "    rate = successful_orders / total_sessions\n"
            "ZeroDivisionError: division by zero\n"
            "Total Sessions: 0"
        ),
        "complaints": [
            "My weekly analytics report is broken. It shows an error instead of data.",
        ],
    },
    {
        "id": 7,
        "name": "IndexError — order validation",
        "target_file": "order_service.py",
        "logs": (
            "2024-11-21 10:15:00 ERROR [order_service] Order validation failed\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/order_service.py\", line 55, in validate_order\n"
            '    if order["items"][0]["quantity"] < 0:\n'
            "IndexError: list index out of range\n"
            "Items in payload: []"
        ),
        "complaints": [
            "I tried to place an order but got an error. My cart showed items but checkout failed.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_patch_correctness(patch_text: str, target_file: str) -> bool:
    gt = GROUND_TRUTH.get(target_file)
    if not gt:
        return False
    pattern = gt["correct_fix_pattern"]
    text_lower = patch_text.lower()
    if isinstance(pattern, list):
        return any(p.lower() in text_lower for p in pattern)
    return pattern.lower() in text_lower


def _run_single(tc: dict) -> dict:
    state = create_initial_state(complaints=tc["complaints"], logs=tc["logs"])
    t0 = time.time()
    try:
        result = pipeline_app.invoke(state)
        elapsed = time.time() - t0
        patch_correct = _check_patch_correctness(
            result.get("code_patch", ""), tc["target_file"]
        )
        # False positive: tests passed but patch doesn't contain the correct pattern
        false_positive = bool(result.get("tests_passed")) and not patch_correct
        return {
            "id": tc["id"],
            "name": tc["name"],
            "target_file": tc["target_file"],
            "tests_passed": bool(result.get("tests_passed")),
            "escalated": bool(result.get("escalate_to_human")),
            "retry_count": result.get("retry_count", 0),
            "patch_correct": patch_correct,
            "false_positive": false_positive,
            "elapsed": round(elapsed, 1),
            "severity": result.get("severity", ""),
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "id": tc["id"],
            "name": tc["name"],
            "target_file": tc["target_file"],
            "tests_passed": False,
            "escalated": False,
            "retry_count": 0,
            "patch_correct": False,
            "false_positive": False,
            "elapsed": round(elapsed, 1),
            "severity": "",
            "error": str(e),
        }


def _compute_metrics(scenario_results: list) -> dict:
    n = len(scenario_results)
    if n == 0:
        return {}

    passed = [r for r in scenario_results if r["tests_passed"]]
    correct = [r for r in scenario_results if r["patch_correct"]]
    first_attempt = [r for r in scenario_results if r["tests_passed"] and r["retry_count"] <= 1]
    retried = [r for r in scenario_results if r["retry_count"] > 1]
    retry_success = [r for r in retried if r["tests_passed"]]
    false_positives = [r for r in scenario_results if r["false_positive"]]
    escalated = [r for r in scenario_results if r["escalated"]]

    return {
        "total_cases": n,
        "patch_correctness_pct": round(len(correct) / n * 100, 1),
        "first_attempt_success_rate": round(len(first_attempt) / n * 100, 1),
        "retry_success_rate": round(len(retry_success) / max(len(retried), 1) * 100, 1),
        "false_positive_rate": round(len(false_positives) / max(len(passed), 1) * 100, 1),
        "avg_run_time_seconds": round(sum(r["elapsed"] for r in scenario_results) / n, 1),
        "escalation_rate": round(len(escalated) / n * 100, 1),
    }


def _print_table(scenario_results: list, metrics: dict) -> None:
    print("\n" + "=" * 80)
    print("  BENCHMARK RESULTS")
    print("=" * 80)
    header = f"{'#':<3} {'Name':<38} {'File':<24} {'Pass':<5} {'Correct':<8} {'Retries':<8} {'Time':<6}"
    print(header)
    print("-" * 80)
    for r in scenario_results:
        status = "✓" if r["tests_passed"] else ("ESC" if r["escalated"] else "✗")
        correct = "✓" if r["patch_correct"] else "✗"
        fp_flag = " ⚠FP" if r["false_positive"] else ""
        err = f" ERR: {r['error'][:20]}" if r["error"] else ""
        print(
            f"{r['id']:<3} {r['name'][:37]:<38} {r['target_file']:<24} "
            f"{status:<5} {correct + fp_flag:<8} {r['retry_count']:<8} {r['elapsed']:.1f}s{err}"
        )
    print("=" * 80)
    print("\n  AGGREGATE METRICS")
    print("-" * 40)
    print(f"  Patch correctness:          {metrics.get('patch_correctness_pct', 0):.1f}%")
    print(f"  First-attempt success rate: {metrics.get('first_attempt_success_rate', 0):.1f}%")
    print(f"  Retry success rate:         {metrics.get('retry_success_rate', 0):.1f}%")
    print(f"  False positive rate:        {metrics.get('false_positive_rate', 0):.1f}%")
    print(f"  Avg run time:               {metrics.get('avg_run_time_seconds', 0):.1f}s")
    print(f"  Escalation rate:            {metrics.get('escalation_rate', 0):.1f}%")
    print("=" * 80 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_benchmark(max_cases: int = 7, save_history: bool = False, case_ids: list = None) -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    cases = TEST_CASES[:max_cases]
    if case_ids:
        cases = [tc for tc in cases if tc["id"] in case_ids]

    print(f"\nRunning benchmark: {len(cases)} test case(s)...")
    scenario_results = []
    for i, tc in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {tc['name']} ...", end=" ", flush=True)
        result = _run_single(tc)
        scenario_results.append(result)
        status = "PASS" if result["tests_passed"] else ("ESCALATED" if result["escalated"] else "FAIL")
        print(f"{status} ({result['elapsed']:.1f}s)")

    metrics = _compute_metrics(scenario_results)
    _print_table(scenario_results, metrics)

    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "scenarios": scenario_results,
    }

    latest_path = os.path.join(RESULTS_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Results saved to {latest_path}")

    if save_history:
        history_path = os.path.join(RESULTS_DIR, "history.jsonl")
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        print(f"Appended to {history_path}")

    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the incident response benchmark suite.")
    parser.add_argument("--max", type=int, default=7, help="Maximum number of test cases to run (default: 7)")
    parser.add_argument("--cases", type=int, nargs="+", metavar="ID", help="Run only specific case IDs (e.g. --cases 7)")
    parser.add_argument("--save-history", action="store_true", help="Append results to history.jsonl")
    args = parser.parse_args()
    run_benchmark(max_cases=args.max, save_history=args.save_history, case_ids=args.cases)
