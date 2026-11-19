import json
from dataclasses import replace
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from tests.benchmark.real import adapter, run_benchmark
from tests.benchmark.real.cache import TrialCache
from tests.benchmark.real.manifest import Bug


@pytest.fixture
def bug():
    return Bug(
        "tqdm-1", "https://github.com/tqdm/tqdm", "a" * 40, "b" * 40,
        "tqdm/lib.py", "tqdm/tests/test_lib.py", ("tqdm/tests/test_lib.py",),
        ("tqdm/tests/test_lib.py::test_regression",), ("tqdm/tests/test_lib.py::test_control",),
    )


def test_manifest_requires_pinned_commits_and_test_only_oracle(bug):
    with pytest.raises(ValueError, match="full Git commit"):
        replace(bug, fixed_commit="HEAD")
    with pytest.raises(ValueError, match="canonical repository-relative"):
        replace(bug, oracle_files=("tqdm/../lib.py",))
    with pytest.raises(ValueError, match="stay in the test tree"):
        replace(bug, oracle_files=("tqdm/another_module.py",))


def test_docker_reports_exact_node_outcomes(monkeypatch, bug, tmp_path):
    failing, = bug.fail_to_pass
    passing, = bug.pass_to_pass
    payload = {failing: {"status": "failed"}, passing: {"status": "passed"}}

    def run(command, **kwargs):
        assert "--network=none" in command
        assert "--pull=never" in command
        assert "--user=65534:65534" in command
        assert all(str(tmp_path) in mount for mount in (
            command[index + 1] for index, argument in enumerate(command) if argument == "--mount"
        ))
        return CompletedProcess(command, 1, f"...{adapter.PREFIX}{json.dumps(payload)}\n", "")

    monkeypatch.setattr(adapter.subprocess, "run", run)
    run = adapter.docker_tests(tmp_path, tmp_path, (failing, passing))
    assert run.status(failing) == "failed"
    assert run.status(passing) == "passed"
    assert run.status("uncollected") is None


def test_validate_requires_fail_to_pass_and_pass_to_pass(monkeypatch, bug):
    failing, = bug.fail_to_pass
    passing, = bug.pass_to_pass
    runs = {
        bug.buggy_commit: adapter.TestRun({failing: {"status": "failed"}, passing: {"status": "passed"}}, ""),
        bug.fixed_commit: adapter.TestRun({failing: {"status": "passed"}, passing: {"status": "passed"}}, ""),
    }
    monkeypatch.setattr(adapter, "evaluate_revision", lambda repo, bug, revision, nodes: runs[revision])
    assert adapter.validate(Path("unused"), bug)["valid"]
    runs[bug.buggy_commit].outcomes[passing]["status"] = "failed"
    assert not adapter.validate(Path("unused"), bug)["valid"]


def test_prompt_uses_buggy_source_only_and_excludes_oracle(monkeypatch, bug):
    failing, = bug.fail_to_pass
    trace = {
        "status": "failed",
        "exception": "AssertionError",
        "frames": [[bug.test_file, 1], [bug.source_path, 1]],
        "calls": [[bug.source_path, 2, "main"]],
    }
    monkeypatch.setattr(
        adapter, "evaluate_revision",
        lambda repo, bug, revision, nodes, **options: adapter.TestRun({failing: trace}, "EXPECTED_SECRET"),
    )

    def read(repo, *args):
        assert args == ("show", f"{bug.buggy_commit}:{bug.source_path}")
        return b"buggy_line()\ndef main():\n"

    monkeypatch.setattr(adapter, "git", read)
    prompt = adapter.incident_input(Path("unused"), bug)
    assert "buggy_line()" in prompt["logs"]
    assert "Observed call main" in prompt["logs"]
    assert bug.test_file not in prompt["logs"]
    assert "EXPECTED_SECRET" not in prompt["logs"]
    assert prompt["complaints"][0].startswith("[Synthetic complaint]")


def test_trial_cache_preserves_completed_records_and_isolates_configuration(tmp_path):
    cache = TrialCache(tmp_path, {"model": "first"})
    assert cache.read("tqdm-1", 1) is None
    assert cache.save("tqdm-1", 1, {"resolved": False}) == {"resolved": False}
    assert cache.save("tqdm-1", 1, {"resolved": True}) == {"resolved": False}
    assert cache.read("tqdm-1", 2) is None
    assert TrialCache(tmp_path, {"model": "second"}).read("tqdm-1", 1) is None


def test_run_resumes_missing_trials_after_rate_limit(monkeypatch, bug, tmp_path):
    completion = {
        "resolved": True, "attempts": 1, "retries": 0, "runtime_seconds": 1.0,
        "failure_category": None,
    }
    calls = []

    def run(repo, bug, number):
        calls.append(number)
        if calls == [1, 2]:
            raise run_benchmark.BenchmarkInterrupted("rate limit")
        return completion

    monkeypatch.setenv("GROQ_API_KEY", "unit-test-placeholder")
    monkeypatch.setattr(run_benchmark, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(run_benchmark, "git", lambda *args: b"a" * 40)
    monkeypatch.setattr(run_benchmark.subprocess, "check_output", lambda *args, **kwargs: "image-id")
    monkeypatch.setattr(run_benchmark, "run_trial", run)
    args = SimpleNamespace(repos=tmp_path, trials=2)

    with pytest.raises(SystemExit) as error:
        run_benchmark.run_all(args, [bug])
    assert error.value.code == 2
    run_benchmark.run_all(args, [bug])
    assert calls == [1, 2, 2]
