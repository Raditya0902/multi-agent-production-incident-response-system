"""Validate the final held-out pool with the offline scorer and no model calls."""

import argparse
import json
import subprocess
from functools import partial
from pathlib import Path

from tests.benchmark.real import adapter
from tests.benchmark.real.heldout.manifest import HeldOutBug
from tests.benchmark.real.manifest import DATASET


def validate_case(repos: Path, path: Path) -> dict:
    bug = HeldOutBug.read(path)
    repo = repos / f"{bug.project}.git"
    validation = adapter.validate(repo, bug)
    if not validation["valid"]:
        raise ValueError(f"{bug.id}: buggy/fixed validation did not reproduce.")
    source = adapter.git(repo, "show", f"{bug.buggy_commit}:{bug.source_path}").decode()
    if not source.endswith("\n"):
        source += "\n"
    unchanged = (
        f"===FILE===\n{bug.source_path}\n===ORIGINAL===\n{source}"
        f"===FIXED===\n{source}===EXPLANATION===\nUnchanged validation control."
    )
    result = adapter.score_candidate(repo, bug, unchanged)
    if result["fail_to_pass"] or not result["pass_to_pass"]:
        raise ValueError(f"{bug.id}: scorer did not reject unchanged source with passing controls.")
    return {"id": bug.id, "validation": validation, "unchanged": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).parent
    adapter.IMAGE = "incident-real-heldout:v1-pool"
    image = subprocess.check_output([
        "docker", "image", "inspect", adapter.IMAGE, "--format", "{{.Id}}",
    ], text=True).strip()
    check = partial(validate_case, args.repos)
    cases = []
    for path in sorted((folder / "manifests").glob("*.json")):
        cases.append(check(path))
        print(f"{path.stem} validated", flush=True)
    payload = {"bugsinpy_commit": DATASET, "evaluator_image": image, "cases": cases}
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
