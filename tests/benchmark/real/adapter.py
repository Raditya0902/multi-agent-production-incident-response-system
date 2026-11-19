"""Stage and evaluate a pinned checkout without exposing the test oracle."""

import ast
import json
import re
import shutil
import subprocess
import tarfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from agents.execution_agent import parse_code_patch
from agents.source_context import production_path
from tests.benchmark.real.manifest import IMAGE
from tests.benchmark.real.report_plugin import PREFIX
from tests.benchmark.scoring import PatchError, apply_replacement, patch_section


TIMEOUT = 110
SYNTHETIC_COMPLAINT = "[Synthetic complaint] A reproducible failure interrupts a normal workflow."
RUNNER_SOURCE = Path(__file__).with_name("report_plugin.py")


class EvaluationError(RuntimeError):
    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category = category


@dataclass(frozen=True)
class TestRun:
    outcomes: dict
    output: str

    def status(self, node: str) -> str | None:
        return self.outcomes.get(node, {}).get("status")


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE, timeout=60)


@contextmanager
def checkout(repo: Path, revision: str):
    with TemporaryDirectory(prefix="incident-real-") as directory:
        staging = Path(directory).resolve()
        staging.chmod(0o755)
        workspace = staging / "checkout"
        workspace.mkdir()
        archive = staging / "tree.tar"
        with archive.open("wb") as file:
            subprocess.run(
                ["git", "-C", str(repo), "archive", "--format=tar", revision],
                stdout=file, stderr=subprocess.PIPE, check=True, timeout=60,
            )
        with tarfile.open(archive) as tree:
            tree.extractall(workspace, filter="data")
        archive.unlink()
        runner = staging / "runner"
        runner.mkdir()
        shutil.copyfile(RUNNER_SOURCE, runner / RUNNER_SOURCE.name)
        yield workspace, runner


def checked_path(workspace: Path, relative: str) -> Path:
    path = workspace / relative
    if path.resolve() != path:
        raise EvaluationError("test_environment_failure", f"Symlink in staged path: {relative}")
    return path


def add_oracle(repo: Path, bug, workspace: Path) -> None:
    for file in bug.oracle_files:
        path = checked_path(workspace, file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git(repo, "show", f"{bug.fixed_commit}:{file}"))


def docker_tests(workspace: Path, runner: Path, nodes: tuple[str, ...], *, collect_only=False, trace=False) -> TestRun:
    name = f"incident-real-{uuid4().hex}"
    command = [
        "docker", "run", "--rm", "--name", name, "--pull=never",
        "--network=none", "--read-only", "--user=65534:65534",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777",
        "--memory=768m", "--cpus=1", "--pids-limit=96",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--mount", f"type=bind,source={workspace},target=/workspace,readonly",
        "--mount", f"type=bind,source={runner},target=/runner,readonly",
        "--env", "PYTHONPATH=/runner:/workspace",
        "--env", "HOME=/tmp",
    ]
    if trace:
        command.extend(["--env", "INCIDENT_TRACE_SOURCE=1"])
    command.extend([
        "-w", "/workspace", IMAGE, "python", "-B", "-m", "pytest",
        "-q", "--tb=short", "-o", "addopts=", "-p", "no:cacheprovider",
        "-W", "default::pytest.PytestRemovedIn8Warning",
        "-p", "report_plugin",
    ])
    if collect_only:
        command.append("--collect-only")
    command.extend(nodes)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as error:
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise EvaluationError("timeout", "Pytest timed out and container cleanup could not be verified.") from error
        raise EvaluationError("timeout", "Offline pytest exceeded its wall-clock limit.") from error
    except OSError as error:
        raise EvaluationError("test_environment_failure", str(error)) from error

    report_lines = [line.split(PREFIX, 1)[1] for line in result.stdout.splitlines() if PREFIX in line]
    if result.returncode not in (0, 1) or len(report_lines) != 1:
        detail = result.stdout + result.stderr
        raise EvaluationError("test_environment_failure", f"Evaluator exit {result.returncode}\n{detail}")
    try:
        outcomes = json.loads(report_lines[0])
    except ValueError as error:
        raise EvaluationError("test_environment_failure", "Invalid pytest report.") from error
    if not isinstance(outcomes, dict) or not outcomes:
        raise EvaluationError("test_environment_failure", "No tests executed.")
    return TestRun(outcomes, result.stdout + result.stderr)


def evaluate_revision(repo: Path, bug, revision: str, nodes: tuple[str, ...], **options) -> TestRun:
    with checkout(repo, revision) as (workspace, runner):
        add_oracle(repo, bug, workspace)
        return docker_tests(workspace, runner, nodes, **options)


def validate(repo: Path, bug) -> dict:
    nodes = (*bug.fail_to_pass, *bug.pass_to_pass)
    buggy = evaluate_revision(repo, bug, bug.buggy_commit, nodes)
    fixed = evaluate_revision(repo, bug, bug.fixed_commit, nodes)
    before = {node: buggy.status(node) for node in nodes}
    after = {node: fixed.status(node) for node in nodes}
    expected = {node: "failed" if node in bug.fail_to_pass else "passed" for node in nodes}
    return {
        "valid": before == expected and all(status == "passed" for status in after.values()),
        "buggy": before,
        "fixed": after,
    }


def score_candidate(repo: Path, bug, patch_text: str) -> dict:
    target = parse_code_patch(patch_text)["file"]
    with checkout(repo, bug.buggy_commit) as (workspace, runner):
        if target != bug.source_path:
            basename = Path(bug.source_path).name
            if target != basename or len(list(workspace.rglob(basename))) != 1:
                raise EvaluationError("wrong_file", "Candidate targets a different or unsupported source file.")
        source = checked_path(workspace, bug.source_path)
        original = patch_section(patch_text, "ORIGINAL", "FIXED")
        fixed = patch_section(patch_text, "FIXED", "EXPLANATION")
        try:
            updated = apply_replacement(source.read_text(encoding="utf-8"), original, fixed)
            ast.parse(updated, filename=bug.source_path)
        except (PatchError, SyntaxError) as error:
            raise EvaluationError("patch_fails_to_apply", str(error)) from error
        source.write_text(updated, encoding="utf-8")
        add_oracle(repo, bug, workspace)
        tests = (*bug.fail_to_pass, *bug.pass_to_pass)
        run = docker_tests(workspace, runner, tests)

    verdicts = {node: run.status(node) for node in tests}
    if any(status not in {"passed", "failed"} for status in verdicts.values()):
        raise EvaluationError("test_environment_failure", "Some required test nodes did not complete.")
    return {
        "fail_to_pass": all(verdicts[node] == "passed" for node in bug.fail_to_pass),
        "pass_to_pass": all(verdicts[node] == "passed" for node in bug.pass_to_pass),
        "verdicts": verdicts,
    }


def read_buggy_source(repo: Path, revision: str, file: str) -> str | None:
    if not production_path(file):
        return None
    try:
        return git(repo, "show", f"{revision}:{file}").decode("utf-8")
    except (subprocess.CalledProcessError, UnicodeDecodeError):
        return None


def incident_input(repo: Path, bug) -> dict:
    run = evaluate_revision(repo, bug, bug.buggy_commit, bug.fail_to_pass, trace=True)
    logs = []
    sources = {}

    def source_line(file, line):
        if file not in sources:
            sources[file] = (read_buggy_source(repo, bug.buggy_commit, file) or "").splitlines()
        lines = sources[file]
        return lines[line - 1].strip() if 1 <= line <= len(lines) else None

    for node in bug.fail_to_pass:
        if run.status(node) != "failed":
            raise EvaluationError("test_environment_failure", "The pinned buggy baseline no longer reproduces.")
        result = run.outcomes[node]
        logs.append(f"Exception: {result['exception']}")
        for file, line in result["frames"]:
            code = source_line(file, line)
            if code:
                logs.append(f'  File "{file}", line {line}\n    {code}')
        for file, line, function in result["calls"]:
            if not re.fullmatch(r"\w+", function):
                continue
            code = source_line(file, line)
            if code:
                logs.append(f'  Observed call {function} in "{file}", line {line}\n    {code}')
    return {"logs": "\n".join(dict.fromkeys(logs)), "complaints": [SYNTHETIC_COMPLAINT]}
