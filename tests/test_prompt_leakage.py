"""Exercise every live prompt in both graph routes with evaluator-only canaries."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import chromadb
import pytest

from agents import llm
from tests.benchmark import run_benchmark as synthetic
from tests.benchmark.real import adapter, run_benchmark as real
from tests.benchmark.real.manifest import Bug
from tests.benchmark.scoring import Score


HIDDEN = (
    "test_heldout_canary",
    "HELDOUT_ASSERTION_CANARY",
    "P2P_DETAIL_CANARY",
    "UPSTREAM_FIX_CANARY",
    "REFERENCE_FIX_CANARY",
)
PATCH = (
    "===FILE===\napp/module.py\n===ORIGINAL===\n    return result\n"
    "===FIXED===\n    return fallback\n===EXPLANATION===\nBounded change."
)
OUTPUT = "\n".join(HIDDEN)


@pytest.fixture
def prompts(monkeypatch):
    seen = []
    answers = iter([
        '{"correlated_error":"RuntimeError","affected_customers":["Test Customer"]}',
        '{"severity":"P1","severity_reason":"failure"}',
        '{"root_cause":"service failure","relevant_files":["app/module.py"]}',
        PATCH, "Use the existing code.", PATCH, "Hi Test.", "- Add monitoring.",
    ])

    def invoke(messages):
        seen.extend(message.content for message in messages)
        return SimpleNamespace(content=next(answers))

    monkeypatch.setattr(llm, "invoke", invoke)
    yield seen
    assert all(secret not in message for secret in HIDDEN for message in seen)


def test_synthetic_oracle_stays_out_of_all_prompts(monkeypatch, prompts, tmp_path):
    case = {
        "id": 0, "name": "probe", "target_file": "module.py", "complaints": ["service failure"],
        "logs": 'File "/app/module.py", line 2, in main\n    return result',
    }
    monkeypatch.setattr(synthetic, "contract_paths", lambda *args, **kwargs: [])
    source = tmp_path / "app"
    source.mkdir()
    (source / "module.py").write_text("def main():\n    return result\n")
    monkeypatch.setattr(synthetic, "SOURCE", source)
    evaluations = []

    def score(target, patch, *, held_out):
        evaluations.append(held_out)
        if held_out:
            return Score(False, True, OUTPUT)
        return Score(len(evaluations) > 1, True, f"{OUTPUT}\n1 failed in 0.02s")

    monkeypatch.setattr(synthetic, "score_patch", score)
    outcome = synthetic._run_single(case, lambda *args, **kwargs: [])
    assert outcome["status"] == "failed"
    first, last = outcome["diagnostics"]["attempts"]
    assert first["feedback_shown_to_critic"] == "wrong_fix"
    assert last["feedback_shown_to_critic"] is None
    assert all(secret not in str(outcome["diagnostics"]) for secret in HIDDEN)
    assert outcome["score_detail"] == OUTPUT
    assert evaluations == [False, False, True]
    assert any("Service checks failed." in prompt for prompt in prompts)
    assert any("PREVIOUS FIX FAILED" in prompt for prompt in prompts)
    assert any("app/module.py:1-2" in prompt for prompt in prompts)
    assert any("Write a personalized reply" in prompt for prompt in prompts)
    assert any("prevention measures" in prompt for prompt in prompts)


def test_real_oracle_stays_out_of_all_prompts(monkeypatch, prompts, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "example-model")
    failing = "tests/test_heldout_canary.py::test_fail"
    passing = "tests/test_heldout_canary.py::test_pass"
    bug = Bug(
        "project-1", "https://github.com/example/project", "a" * 40, "b" * 40,
        "app/module.py", "tests/test_heldout_canary.py", ("tests/test_heldout_canary.py",),
        (failing,), (passing,),
    )

    def read(repo, operation, spec):
        assert operation == "show"
        assert spec == f"{bug.buggy_commit}:{bug.source_path}"
        return b"def main():\n    return result\n"

    (tmp_path / "app").mkdir()
    (tmp_path / "app/module.py").write_text("def main():\n    return result\n")
    monkeypatch.setattr(real, "checkout", lambda *args: nullcontext((tmp_path, None)))
    monkeypatch.setattr(adapter, "git", read)
    monkeypatch.setattr(adapter, "evaluate_revision", lambda *args, **kwargs: adapter.TestRun({
        failing: {"status": "failed", "exception": "RuntimeError", "frames": [
            [bug.test_file, 1], ["reference_fixes/module.py", 1], [bug.source_path, 2],
        ], "calls": []},
    }, OUTPUT))
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **kwargs: SimpleNamespace(
        create_collection=lambda *args: None,
    ))
    monkeypatch.setattr("rag.vectorstore.retrieve_context_with_scores", lambda *args, **kwargs: [])
    attempts = []

    def score(repo, bug, patch):
        attempts.append(patch)
        return {"fail_to_pass": len(attempts) > 1, "pass_to_pass": len(attempts) > 1,
                "verdicts": {node: "passed" if len(attempts) > 1 else "failed" for node in (failing, passing)},
                "raw_output": OUTPUT}

    monkeypatch.setattr(real, "score_candidate", score)
    outcome = real.run_trial(Path("unused"), bug, 1)
    assert outcome["resolved"]
    first, last = outcome["diagnostics"]["attempts"]
    assert first["feedback_shown_to_critic"] == "wrong_fix"
    assert last["feedback_shown_to_critic"] is None
    assert all(secret not in str(outcome["diagnostics"]) for secret in HIDDEN)
    assert outcome["attempts"] == 2
    assert any("The candidate did not pass the required behavioral checks." in prompt for prompt in prompts)
    assert any("PREVIOUS FIX FAILED" in prompt for prompt in prompts)
    assert any("app/module.py:1-2" in prompt for prompt in prompts)
    assert any("Write a personalized reply" in prompt for prompt in prompts)
    assert any("prevention measures" in prompt for prompt in prompts)
