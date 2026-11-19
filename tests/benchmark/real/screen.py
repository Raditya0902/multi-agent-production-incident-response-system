"""Apply the frozen selection protocol with trusted upstream test oracles."""

import argparse
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path
from time import monotonic

from tests.benchmark.real.adapter import EvaluationError, evaluate_revision, git, validate
from tests.benchmark.real.manifest import DATASET, IMAGE, Bug


PROJECTS = ("tqdm", "PySnooper", "cookiecutter", "black")
EXCLUDED = {"black-16": "Symlink handling crosses a filesystem boundary."}


def candidate(project, directory, repo, repository):
    bug_id = f"{project}-{directory.name}"
    if bug_id in EXCLUDED:
        raise ValueError(EXCLUDED[bug_id])
    metadata = dict(re.findall(r'([a-z_]+)="([^"]*)"', (directory / "bug.info").read_text()))
    before = metadata["buggy_commit_id"]
    after = metadata["fixed_commit_id"]
    changes = [line.split("\t") for line in
               git(repo, "diff", "--numstat", "--no-renames", before, after).decode().splitlines()]
    test_changes = tuple(path for _, _, path in changes if "tests" in Path(path).parts)
    production = [(add, delete, path) for add, delete, path in changes
                  if Path(path).suffix in {".py", ".pyi"} and path not in test_changes]
    if len(production) != 1:
        raise ValueError(f"Expected one production Python file, found {len(production)}.")
    added, deleted, source = production[0]
    if not added.isdecimal() or not deleted.isdecimal() or int(added) + int(deleted) > 35:
        raise ValueError("Production change exceeds the 35-line limit.")

    target = (directory / "run_test.sh").read_text()
    nodes = tuple(re.findall(r"[^\s]+\.py::[^\s]+", target))
    if not nodes:
        unittest = re.findall(r"\b(tests(?:\.\w+)+\.test_\w+)\b", target)
        nodes = tuple(f"{module.replace('.', '/')}.py::{cls}::{test}"
                      for module, cls, test in (node.rsplit(".", 2) for node in unittest))
    files = {node.split("::", 1)[0] for node in nodes}
    if len(files) != 1:
        raise ValueError("BugsInPy does not supply target tests from one pytest-compatible file.")
    return Bug(bug_id, repository, before, after, source, files.pop(), test_changes, nodes, ())


def screen(repo, bug):
    collected = evaluate_revision(repo, bug, bug.fixed_commit, (bug.test_file,), collect_only=True)
    selected_targets = tuple(node for node in collected.outcomes if any(
        node == target or node.startswith(target + "[") for target in bug.fail_to_pass
    ))
    if not selected_targets:
        raise ValueError("No documented target tests collected on the fixed source.")
    controls = tuple(node for node in collected.outcomes if node not in selected_targets)[:8]
    if not controls:
        raise ValueError("No separate pass-to-pass candidates in the target test file.")
    nodes = (*selected_targets, *controls)
    before = evaluate_revision(repo, bug, bug.buggy_commit, nodes)
    after = evaluate_revision(repo, bug, bug.fixed_commit, nodes)
    if any(after.status(node) != "passed" for node in selected_targets):
        raise ValueError("Documented target did not pass on the fixed revision.")
    regressions = tuple(node for node in selected_targets if before.status(node) == "failed")
    if not regressions:
        raise ValueError("Documented target did not fail on the buggy revision.")
    passing = tuple(node for node in controls if before.status(node) == after.status(node) == "passed")[:3]
    if not passing:
        raise ValueError("No control passed on both revisions.")
    selected = replace(bug, fail_to_pass=regressions, pass_to_pass=passing)
    evidence = validate(repo, selected)
    if not evidence["valid"]:
        raise ValueError("Exact-node confirmation did not reproduce both expected verdicts.")
    return selected, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--repos", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if git(args.dataset, "rev-parse", "HEAD").decode().strip() != DATASET:
        parser.error(f"Expected BugsInPy revision {DATASET}")
    image_id = subprocess.check_output(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("--output must be an empty directory.")
    manifests = args.output / "manifests"
    manifests.mkdir(exist_ok=True)
    ledger = []
    accepted = 0
    for project in PROJECTS:
        directory = args.dataset / "projects" / project
        repo = args.repos / f"{project}.git"
        repository = re.search(r'github_url="([^"]+)"', (directory / "project.info").read_text())[1]
        for entry in sorted((directory / "bugs").iterdir(), key=lambda item: int(item.name)):
            bug_id = f"{project}-{entry.name}"
            started = monotonic()
            try:
                bug, evidence = screen(repo, candidate(project, entry, repo, repository))
                (manifests / f"{bug_id}.json").write_text(json.dumps(bug.to_dict(), indent=2) + "\n")
                record = {"id": bug_id, "outcome": "selected", "validation": evidence}
                accepted += 1
            except (ValueError, EvaluationError, FileNotFoundError, subprocess.CalledProcessError) as error:
                record = {"id": bug_id, "outcome": "excluded", "reason": str(error)}
            record["runtime_seconds"] = round(monotonic() - started, 2)
            ledger.append(record)
            print(bug_id, record["outcome"], record.get("reason", "").split("\n", 1)[0], flush=True)
            (args.output / "screening.json").write_text(json.dumps(
                {"bugsinpy_commit": DATASET, "evaluator_image": image_id, "cases": ledger}, indent=2,
            ) + "\n")
            if accepted >= 15:
                return


if __name__ == "__main__":
    main()
