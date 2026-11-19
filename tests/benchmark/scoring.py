"""Stage one candidate and score it against explicit service contracts."""

import ast
import re
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agents.execution_agent import parse_code_patch


SUITE = Path(__file__).resolve().parent
SOURCE = SUITE.parent.parent / "app"
IMAGE = "incident-benchmark-pytest:phase1"
TEST_TIMEOUT = 30


class PatchError(ValueError):
    pass


@dataclass(frozen=True)
class Score:
    passed: bool | None
    used_real_tests: bool
    detail: str


def contract_paths(target: str, held_out: bool) -> list[Path]:
    stem = Path(target).stem
    paths = [SUITE / "service_tests" / f"test_{stem}.py"]
    if held_out:
        paths.append(SUITE / "heldout" / f"test_{stem}_edge.py")
    return paths


def apply_replacement(source: str, original: str, fixed: str) -> str:
    if not original.strip() or not fixed.strip():
        raise PatchError("Patch requires nonempty ORIGINAL and FIXED sections.")
    expected = textwrap.dedent(original.strip("\r\n")).splitlines()
    replacement = textwrap.dedent(fixed.strip("\r\n"))
    lines = source.splitlines(keepends=True)
    matches = []
    for start in range(len(lines) - len(expected) + 1):
        block = "".join(lines[start:start + len(expected)])
        if textwrap.dedent(block).splitlines() == expected:
            matches.append(start)
    if len(matches) != 1:
        raise PatchError("ORIGINAL must match exactly one source block.")
    start = matches[0]
    indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
    return "".join(lines[:start]) + textwrap.indent(replacement, indent) + "\n" + "".join(
        lines[start + len(expected):]
    )


def candidate_source(target: str, patch_text: str) -> str:
    patch = parse_code_patch(patch_text)
    if patch["file"] not in {target, f"app/{target}"}:
        raise PatchError("The candidate targets a different file from the scenario.")
    # The dashboard parser strips leading whitespace on the first line of each
    # section. Read these two bodies intact so multiline indentation survives.
    original = patch_section(patch_text, "ORIGINAL", "FIXED")
    fixed = patch_section(patch_text, "FIXED", "EXPLANATION")
    candidate = apply_replacement((SOURCE / target).read_text(), original, fixed)
    try:
        ast.parse(candidate, filename=target)
    except SyntaxError as error:
        raise PatchError(f"Patched source is invalid Python at line {error.lineno}: {error.msg}") from error
    return candidate


def patch_section(text: str, start: str, end: str) -> str:
    _, _, tail = text.partition(f"==={start}===")
    body, _, _ = tail.partition(f"==={end}===")
    return body


def stage_workspace(workspace: Path, target: str, source: str, paths: list[Path]) -> list[str]:
    package = workspace / "app"
    package.mkdir()
    (package / target).write_text(source)
    for path in paths:
        shutil.copyfile(path, workspace / path.name)
    return [path.name for path in paths]


def run_docker(workspace: Path, tests: list[str]) -> Score:
    name = f"incident-benchmark-{uuid4().hex}"
    command = [
        "docker", "run", "--rm", "--name", name, "--pull=never",
        "--network=none", "--read-only", "--user=65534:65534",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--memory=256m", "--cpus=1", "--pids-limit=64",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--mount", f"type=bind,source={workspace},target=/app,readonly",
        "-w", "/app", IMAGE, "python", "-B", "-m", "pytest",
        "-q", "--tb=short", "-p", "no:cacheprovider", *tests,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=TEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return Score(None, False, "Evaluator timed out and Docker cleanup could not be verified.")
        return Score(None, False, "Evaluator timed out before pytest returned a result.")
    except OSError as error:
        return Score(None, False, f"Docker could not start: {error}")
    detail = result.stdout + result.stderr
    passed = re.search(r"(?m)^(\d+) passed(?:,| in )", result.stdout)
    failed = re.search(r"(?m)^\d+ failed(?:,| in )", result.stdout)
    if result.returncode == 0 and passed and int(passed[1]) == len(tests):
        return Score(True, True, detail)
    if result.returncode == 1 and failed:
        return Score(False, True, detail)
    return Score(None, False, f"Evaluator did not complete the expected tests (exit {result.returncode}).\n{detail}")


def score_patch(target: str, patch: str, *, held_out: bool) -> Score:
    paths = contract_paths(target, held_out)
    if not all(path.is_file() for path in paths):
        return Score(None, False, "Required real pytest contract is missing.")
    try:
        candidate = candidate_source(target, patch)
    except PatchError as error:
        return Score(False, False, str(error))
    except OSError as error:
        return Score(None, False, f"Source is unavailable: {error}")

    with tempfile.TemporaryDirectory(prefix="incident-eval-") as directory:
        workspace = Path(directory).resolve()
        workspace.chmod(0o755)
        tests = stage_workspace(workspace, target, candidate, paths)
        return run_docker(workspace, tests)
