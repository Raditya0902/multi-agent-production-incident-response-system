from pathlib import Path
from subprocess import CompletedProcess

import pytest

from agents.execution_agent import find_real_test_file
from graph import workflow
from rag import vectorstore
from tests.benchmark import run_benchmark as benchmark
from tests.benchmark import scoring
from tests.benchmark.scoring import Score


def test_disagreement_counts_exclude_unscored_and_retry_definitions():
    cases = [
        (True, True, 1), (True, False, 2), (False, True, 2),
        (False, False, 1), (None, True, 1), (None, None, 0),
    ]
    scenarios = [{
        "tests_passed": passed,
        "pattern_match": match,
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "elapsed": 1,
        "escalated": False,
    } for passed, match, attempts in cases]
    metrics = benchmark._compute_metrics(scenarios)

    assert metrics["disagreement_matrix"] == dict(both=1, tests_only=1, pattern_only=1, neither=1)
    assert metrics["matrix_unscored_count"] == metrics["invalid_count"] == 2
    assert metrics["resolved_count"] == 2
    assert metrics["resolved_pct"] == 33.3
    assert metrics["first_attempt_success_rate"] == 16.7
    assert metrics["retry_success_rate"] == 50.0


def test_missing_contract_never_invokes_pipeline_or_fallback(monkeypatch, tmp_path):
    missing = tmp_path / "missing.py"
    monkeypatch.setattr(benchmark, "contract_paths", lambda *args, **kwargs: [missing])
    monkeypatch.setattr(scoring, "contract_paths", lambda *args, **kwargs: [missing])

    def unexpected(*args, **kwargs):
        pytest.fail("Missing contracts must stop evaluation before execution")

    monkeypatch.setattr(benchmark, "build_workflow", unexpected)
    monkeypatch.setattr(scoring, "run_docker", unexpected)
    scenario = benchmark._run_single(benchmark.TEST_CASES[0], unexpected)
    assert scenario["status"] == "invalid"
    assert scenario["tests_passed"] is None
    assert scenario["used_real_tests"] is False
    assert scoring.score_patch("data_processing.py", "", held_out=False).passed is None


def test_final_score_uses_heldout_only_after_graph_finishes(monkeypatch):
    events = []
    patch = "===FIXED===\nif index < len(items): pass"

    def evaluate(target, candidate, *, held_out):
        assert candidate == patch
        events.append("held_out" if held_out else "smoke")
        return Score(not held_out, True, "held-out failure" if held_out else "smoke pass")

    def finish_graph(state):
        assert "held_out" not in events
        events.append("graph_finished")
        return {"status": "complete"}

    monkeypatch.setattr(benchmark, "score_patch", evaluate)
    monkeypatch.setattr(benchmark, "root_cause_agent", lambda state, *, retrieve: retrieve())
    monkeypatch.setattr(workflow, "correlation_agent", lambda state: {"correlated_error": "bad index"})
    monkeypatch.setattr(workflow, "severity_agent", lambda state: {"severity": "P1"})
    monkeypatch.setattr(workflow, "fix_generator_agent", lambda state: {"code_patch": patch})
    monkeypatch.setattr(workflow, "customer_response_agent", lambda state: {"customer_replies": []})
    monkeypatch.setattr(workflow, "incident_report_agent", finish_graph)
    result = benchmark._run_single(benchmark.TEST_CASES[0], lambda: {"root_cause": "missing check"})
    assert events == ["smoke", "graph_finished", "held_out"]
    assert result["tests_passed"] is False
    assert result["pattern_match"] is True
    assert result["used_real_tests"] is True
    assert result["attempts"] == 1
    assert result["retries"] == 0


def test_dashboard_discovery_excludes_benchmark_contracts():
    for scenario in benchmark.TEST_CASES:
        found = find_real_test_file(scenario["target_file"])
        assert found is None or "benchmark" not in Path(found).parts


def test_docker_success_requires_all_contract_tests_to_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(
        scoring.subprocess, "run",
        lambda *args, **kwargs: CompletedProcess(args, 0, "1 passed, 1 skipped in 0.01s\n", ""),
    )
    score = scoring.run_docker(tmp_path, ["test_service.py", "test_edge.py"])
    assert score.passed is None
    assert score.used_real_tests is False


def test_benchmark_queries_only_static_seed_without_using_dashboard_collection(monkeypatch, tmp_path):
    from numpy import array

    class EmbeddingModel:
        def encode(self, values):
            return array([1.0, 0.0] if isinstance(values, str) else [[1.0, 0.0]] * len(values))

    def dashboard_collection():
        pytest.fail("Benchmark touched the dashboard collection")

    def run_case(case, retrieve):
        documents = [doc for doc, _ in retrieve("sample", top_k=5)]
        assert documents == ["Static knowledge."]
        return {"status": "resolved", "elapsed": 0, "error": None}

    corpus = tmp_path / "past_incidents"
    (corpus / "real").mkdir(parents=True)
    (corpus / "static.md").write_text("Static knowledge.")
    (corpus / "real" / "downloaded.md").write_text("Downloaded locally.")
    monkeypatch.setattr(benchmark, "INCIDENTS_DIR", corpus)
    monkeypatch.setattr(benchmark, "_run_single", run_case)
    monkeypatch.setattr(vectorstore, "_get_collection", dashboard_collection)
    monkeypatch.setattr(vectorstore, "get_embedding_model", EmbeddingModel)

    results, seeded, stopped = benchmark._score_cases([benchmark.TEST_CASES[0]] * 2, tmp_path / "chroma")
    assert stopped is None
    assert len(results) == 2
    assert seeded == ["static"]
