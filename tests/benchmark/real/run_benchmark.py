"""Validate frozen BugsInPy cases or explicitly run the auto-approved benchmark."""

import argparse
import collections
import json
import os
import subprocess
from contextlib import closing, nullcontext
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from tests.benchmark.real.adapter import EvaluationError, git, incident_input, score_candidate, validate
from tests.benchmark.real.cache import TrialCache
from tests.benchmark.real.manifest import DATASET, IMAGE, MANIFESTS, Bug
from tests.benchmark.real.screen import PROJECTS


RESULTS = MANIFESTS.parent.parent / "results" / "real"
FEEDBACK = {
    "wrong_file": "The patch targets a different or unsupported source file.",
    "wrong_fix": "The candidate did not pass the required behavioral checks.",
    "patch_fails_to_apply": "ORIGINAL must match exactly one source block and FIXED must parse as Python.",
}


class BenchmarkInterrupted(RuntimeError):
    pass


def run_trial(repo: Path, bug: Bug, trial: int) -> dict:
    import chromadb

    from agents import _is_daily_quota_error, _is_rate_limit_error, is_using_fallback
    from agents.root_cause_agent import root_cause_agent
    from agents.state import create_initial_state
    from graph.workflow import build_workflow
    from rag.vectorstore import retrieve_context_with_scores

    started = monotonic()
    category = None
    scores = {}
    attempts = 0
    state = {}

    def execute(state):
        nonlocal attempts, category, scores
        attempts += 1
        scores = {}
        try:
            scores = score_candidate(repo, bug, state["code_patch"])
            passed = scores["fail_to_pass"] and scores["pass_to_pass"]
            category = None if passed else "wrong_fix"
        except EvaluationError as error:
            category = error.category
            if category not in FEEDBACK:
                raise
            passed = False
        return {
            "tests_passed": passed,
            "used_real_tests": bool(scores),
            "retry_count": attempts,
            "test_results": "Behavioral checks passed." if passed else FEEDBACK[category],
        }

    diagnostic = None
    try:
        state = create_initial_state(**incident_input(repo, bug))
        with TemporaryDirectory(prefix="incident-real-rag-") as path:
            client = chromadb.PersistentClient(path=path)
            with closing(client) if hasattr(client, "close") else nullcontext(client):
                collection = client.create_collection("real_benchmark_empty")
                retrieve = partial(retrieve_context_with_scores, collection=collection)
                diagnose = partial(root_cause_agent, retrieve=retrieve)
                workflow = build_workflow(diagnose=diagnose, execute=execute)
                for step in workflow.stream(state, stream_mode="updates"):
                    for update in step.values():
                        state.update(update)
    except EvaluationError as error:
        category = error.category
        diagnostic = str(error).splitlines()[0]
    except (OSError, subprocess.SubprocessError) as error:
        category = "test_environment_failure"
        diagnostic = str(error)
    except Exception as error:
        message = str(error)
        if (_is_rate_limit_error(message.lower()) or _is_daily_quota_error(message.lower())
                or getattr(error, "status_code", None) in {401, 403}):
            raise BenchmarkInterrupted(message.splitlines()[0]) from error
        diagnostic = message.splitlines()[0]
        if not scores and category is None:
            category = "pipeline_error"

    resolved = bool(scores.get("fail_to_pass") and scores.get("pass_to_pass"))
    return {
        "bug": bug.id,
        "trial": trial,
        "approval_mode": "auto_approve",
        "rag": {"mode": "throwaway_empty", "auto_ingest": False},
        "provider": os.getenv("FALLBACK_LLM_PROVIDER") if is_using_fallback() else "groq",
        "resolved": resolved,
        "fail_to_pass": scores.get("fail_to_pass"),
        "pass_to_pass": scores.get("pass_to_pass"),
        "test_verdicts": scores.get("verdicts", {}),
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "runtime_seconds": round(monotonic() - started, 2),
        "failure_category": None if resolved else category,
        "diagnostic": diagnostic,
        "generated_patch": state.get("code_patch", ""),
    }


def summarize(results: list[dict], requested: int) -> dict:
    total = len(results)
    resolved = [record for record in results if record["resolved"]]
    return {
        "requested": requested,
        "completed": total,
        "missing": requested - total,
        "mean_resolve_rate": len(resolved) / total if total else None,
        "first_attempt_rate": sum(row["attempts"] == 1 for row in resolved) / total if total else None,
        "retry_rate": sum(row["retries"] > 0 for row in results) / total if total else None,
        "average_runtime_seconds": sum(row["runtime_seconds"] for row in results) / total if total else None,
        "failures": dict(collections.Counter(row["failure_category"] for row in results if not row["resolved"])),
    }


def select_bugs(ids, max_bugs, directory=MANIFESTS):
    bugs = [Bug.read(path) for path in directory.glob("*.json")]
    bugs.sort(key=lambda bug: (PROJECTS.index(bug.project), int(bug.id.rsplit("-", 1)[1])))
    if ids:
        unknown = set(ids) - {bug.id for bug in bugs}
        if unknown:
            raise ValueError(f"Unknown frozen bug IDs: {', '.join(sorted(unknown))}")
        bugs = [bug for bug in bugs if bug.id in ids]
    return bugs[:max_bugs]


def run_all(args, bugs):
    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("Set GROQ_API_KEY in the ignored .env before running the benchmark.")
    image_id = subprocess.check_output(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
    configuration = {
        "dataset": DATASET,
        "evaluator_image": image_id,
        "evaluator_commit": git(Path(__file__).parent, "rev-parse", "HEAD").decode().strip(),
        "provider": "groq",
        "fallback": os.getenv("FALLBACK_LLM_PROVIDER", ""),
        "model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        "temperature": os.getenv("GROQ_TEMPERATURE", "0.2"),
        "max_tokens": os.getenv("GROQ_MAX_TOKENS", "4096"),
        "attempt_limit": os.getenv("MAX_RETRY_ATTEMPTS", "3"),
    }
    pending = False
    results = []
    print(f"BugsInPy | AUTO-APPROVE | {configuration['model']}", flush=True)
    for bug in bugs:
        provenance = {**configuration, "manifest": bug.to_dict()}
        cache = TrialCache(RESULTS, provenance)
        for number in range(1, args.trials + 1):
            result = cache.read(bug.id, number)
            if result is None and not pending:
                try:
                    result = run_trial(args.repos / f"{bug.project}.git", bug, number)
                    result = cache.save(bug.id, number, {**result, "configuration": provenance})
                except BenchmarkInterrupted as error:
                    print(f"Paused at {bug.id} trial {number}: {error}", flush=True)
                    pending = True
            if result is None:
                print(f"{bug.id} trial {number}: pending", flush=True)
                continue
            results.append(result)
            verdict = "resolved" if result["resolved"] else result["failure_category"]
            print(f"{bug.id} trial {number}: {verdict}, {result['attempts']} attempts, "
                  f"{result['runtime_seconds']:.2f}s", flush=True)
    print(json.dumps(summarize(results, len(bugs) * args.trials), indent=2))
    if pending:
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate", "run"))
    parser.add_argument("--repos", type=Path, required=True, help="Directory containing <project>.git mirrors")
    parser.add_argument("--bugs", nargs="+", help="Specific frozen BugsInPy IDs")
    parser.add_argument("--max", type=int, help="Maximum number of frozen bugs")
    parser.add_argument("--trials", type=int, default=3, help="Trials per bug in run mode")
    args = parser.parse_args()
    if args.trials < 1 or (args.max is not None and args.max < 1):
        parser.error("--max and --trials must be positive.")
    try:
        bugs = select_bugs(args.bugs, args.max)
    except ValueError as error:
        parser.error(str(error))
    if not bugs:
        parser.error("No frozen BugsInPy manifests were found.")
    if args.mode == "run":
        run_all(args, bugs)
        return

    invalid = []
    for bug in bugs:
        try:
            evidence = validate(args.repos / f"{bug.project}.git", bug)
        except (EvaluationError, OSError, subprocess.SubprocessError) as error:
            evidence = {"valid": False, "reason": str(error).splitlines()[0]}
        print(json.dumps({"bug": bug.id, **evidence}), flush=True)
        if not evidence["valid"]:
            invalid.append(bug.id)
    print(f"{len(bugs) - len(invalid)}/{len(bugs)} validated without model calls.")
    if invalid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
