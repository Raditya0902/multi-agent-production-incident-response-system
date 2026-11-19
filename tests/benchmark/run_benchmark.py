"""
Benchmark runner — evaluates the full pipeline against all 7 test cases.

Usage:
    python -m tests.benchmark.run_benchmark
    python -m tests.benchmark.run_benchmark --save-history
    python -m tests.benchmark.run_benchmark --max 3   # run only first N cases

Outputs:
    Printed table + tests/benchmark/results/synthetic-latest.json
    With --save-history: also appends to tests/benchmark/results/synthetic-history.jsonl
"""

import argparse
import json
import os
import sys
import time
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.state import create_initial_state
from agents.root_cause_agent import root_cause_agent
from graph.workflow import build_workflow
from rag.ingestion import INCIDENTS_DIR, _load_docs_from_dir
from rag.vectorstore import add_documents, retrieve_context_with_scores
from tests.benchmark.ground_truth import GROUND_TRUTH
from tests.benchmark.scoring import Score, contract_paths, score_patch

RESULTS_DIR = Path(__file__).parent / "results"

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


def _run_single(tc: dict, retrieve) -> dict:
    target = tc["target_file"]
    state = create_initial_state(complaints=tc["complaints"], logs=tc["logs"])
    started = time.monotonic()
    pipeline_error = None
    smoke_score = None

    def execute(state):
        nonlocal smoke_score
        smoke_score = score_patch(target, state["code_patch"], held_out=False)
        if smoke_score.passed is None:
            # An unusable evaluator cannot supply meaningful Critic feedback.
            raise RuntimeError(smoke_score.detail)
        return {
            "tests_passed": smoke_score.passed,
            "used_real_tests": smoke_score.used_real_tests,
            "test_results": smoke_score.detail,
            "retry_count": state["retry_count"] + 1,
            "status": "tests_passed" if smoke_score.passed else "tests_failed",
        }

    if not all(path.is_file() for path in contract_paths(target, held_out=True)):
        score = Score(None, False, "Required real pytest contract is missing.")
    else:
        pipeline = build_workflow(
            diagnose=partial(root_cause_agent, retrieve=retrieve), execute=execute,
        )
        try:
            for step in pipeline.stream(state, stream_mode="updates"):
                for update in step.values():
                    state.update(update)
        except Exception as error:
            pipeline_error = str(error)

        if smoke_score is not None and smoke_score.passed is None:
            score = smoke_score
        elif state["code_patch"]:
            score = score_patch(target, state["code_patch"], held_out=True)
        else:
            score = Score(None, False, "Pipeline produced no candidate to score.")

    patch = state["code_patch"]
    attempts = state["retry_count"]
    if smoke_score is not None and smoke_score.passed is None:
        attempts += 1
    return {
        "id": tc["id"],
        "name": tc["name"],
        "target_file": target,
        "status": {None: "invalid", False: "failed", True: "resolved"}[score.passed],
        "tests_passed": score.passed,
        "pattern_match": _check_patch_correctness(patch, target) if patch else None,
        "used_real_tests": score.used_real_tests,
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "elapsed": round(time.monotonic() - started, 2),
        "generated_patch": patch,
        "escalated": state["escalate_to_human"],
        "severity": state["severity"],
        "score_detail": score.detail,
        "error": pipeline_error,
    }


def _compute_metrics(scenarios: list[dict]) -> dict:
    matrix = {"both": 0, "tests_only": 0, "pattern_only": 0, "neither": 0}
    cells = {
        (True, True): "both",
        (True, False): "tests_only",
        (False, True): "pattern_only",
        (False, False): "neither",
    }
    for scenario in scenarios:
        cell = cells.get((scenario["tests_passed"], scenario["pattern_match"]))
        if cell:
            matrix[cell] += 1

    total = len(scenarios)
    passed = [s for s in scenarios if s["tests_passed"] is True]
    invalid = sum(s["tests_passed"] is None for s in scenarios)
    retried = [s for s in scenarios if s["retries"] > 0]

    def pct(count, denominator):
        return round(100 * count / denominator, 1) if denominator else None

    return {
        "total_cases": total,
        "resolved_count": len(passed),
        "invalid_count": invalid,
        "resolved_pct": pct(len(passed), total),
        "pattern_match_pct": pct(
            sum(s["pattern_match"] is True for s in scenarios),
            sum(s["pattern_match"] is not None for s in scenarios),
        ),
        "first_attempt_success_rate": pct(sum(s["attempts"] == 1 for s in passed), total),
        "retry_success_rate": pct(sum(s["tests_passed"] is True for s in retried), len(retried)),
        "avg_run_time_seconds": round(sum(s["elapsed"] for s in scenarios) / total, 2) if total else None,
        "escalation_rate": pct(sum(s["escalated"] for s in scenarios), total),
        "disagreement_matrix": matrix,
        "matrix_unscored_count": total - sum(matrix.values()),
    }


def _print_metrics(metrics: dict) -> None:
    print(f"Resolved (service + held-out pytest): {metrics['resolved_count']}/{metrics['total_cases']}")
    print(f"Invalid / unscored: {metrics['invalid_count']}")
    rate = metrics["pattern_match_pct"]
    print("Pattern match: " + (f"{rate:.1f}%" if rate is not None else "unavailable"))
    matrix = metrics["disagreement_matrix"]
    print("Tests pass x pattern match")
    print(f"  Both {matrix['both']} | Tests only {matrix['tests_only']} | "
          f"Pattern only {matrix['pattern_only']} | Neither {matrix['neither']}")
    print(f"  Matrix unscored: {metrics['matrix_unscored_count']}")


def _score_cases(cases, vector_dir):
    import chromadb

    client = chromadb.PersistentClient(path=str(vector_dir))
    collection = client.create_collection("synthetic_static", metadata={"hnsw:space": "cosine"})
    docs = _load_docs_from_dir(INCIDENTS_DIR)
    if not docs:
        raise RuntimeError("The static past_incidents/ knowledge base is empty.")
    add_documents(docs, collection=collection)
    retrieve = partial(retrieve_context_with_scores, collection=collection)

    results = []
    for case in cases:
        print(f"  [{case['id']}] {case['name']} ...", end=" ", flush=True)
        result = _run_single(case, retrieve)
        results.append(result)
        print(f"{result['status'].upper()} ({result['elapsed']:.2f}s)")
        if result["error"]:
            print(f"    {result['error'].splitlines()[0]}")
        elif result["status"] == "invalid":
            print(f"    {result['score_detail'].splitlines()[0]}")
    return results, [doc["id"] for doc in docs]


def run_benchmark(max_cases: int = 7, save_history: bool = False, case_ids: list = None) -> dict:
    cases = TEST_CASES[:max_cases]
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
    print(f"Synthetic regression suite | benchmark mode: AUTO-APPROVE | {len(cases)} case(s)", flush=True)

    with TemporaryDirectory(prefix="incident-benchmark-chroma-") as vector_dir:
        scenarios, seed_ids = _score_cases(cases, vector_dir)
    metrics = _compute_metrics(scenarios)
    _print_metrics(metrics)

    payload = {
        "schema_version": 2,
        "suite": "synthetic_regression",
        "approval_mode": "auto_approve",
        "rag": {"mode": "throwaway_static", "seed_ids": seed_ids, "auto_ingest": False},
        "run_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "scenarios": scenarios,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    latest = RESULTS_DIR / "synthetic-latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Results saved to {latest}")

    if save_history:
        history = RESULTS_DIR / "synthetic-history.jsonl"
        with history.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        print(f"Appended to {history}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the incident response benchmark suite.")
    parser.add_argument("--max", type=int, default=7, help="Maximum number of test cases to run (default: 7)")
    parser.add_argument("--cases", type=int, nargs="+", metavar="ID", help="Run only specific case IDs (e.g. --cases 7)")
    parser.add_argument("--save-history", action="store_true", help="Append results to history.jsonl")
    args = parser.parse_args()
    run_benchmark(max_cases=args.max, save_history=args.save_history, case_ids=args.cases)
