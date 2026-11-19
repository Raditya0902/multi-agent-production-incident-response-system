import json
import subprocess
import sys

import pytest

from tests.benchmark.run_benchmark import TEST_CASES
from tests.benchmark.scoring import SOURCE, SUITE, apply_replacement, contract_paths, stage_workspace


@pytest.mark.parametrize("target", [case["target_file"] for case in TEST_CASES])
def test_service_contract_fails_before_and_passes_after(target, tmp_path):
    original = (SOURCE / target).read_text()
    reference = json.loads((SUITE / "reference_fixes" / target).with_suffix(".json").read_text())
    corrected = apply_replacement(original, reference["original"], reference["fixed"])

    def run(label, source, held_out):
        workspace = tmp_path / label
        workspace.mkdir()
        tests = stage_workspace(workspace, target, source, contract_paths(target, held_out))
        return subprocess.run(
            [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
            cwd=workspace, timeout=30, capture_output=True, text=True,
        )

    before = run("before", original, held_out=False)
    assert before.returncode == 1, before.stdout + before.stderr
    assert "1 failed" in before.stdout, before.stdout

    after = run("after", corrected, held_out=True)
    assert after.returncode == 0, after.stdout + after.stderr
    assert "2 passed" in after.stdout, after.stdout
