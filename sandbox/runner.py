"""Run pytest in a disposable workspace with an explicit execution backend."""

import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

DOCKER_IMAGE = "incident-execution-sandbox:local"
SUBPROCESS_WARNING = (
    "Subprocess sandbox active. Use only trusted patches. "
    "The child process can access the host filesystem and network."
)
_PYTEST_ARGS = ("-m", "pytest", "-v", "--tb=short", "-p", "no:cacheprovider")
_EXCLUDED = {
    "__pycache__", "dev", "data_storage", "chroma_db", "node_modules", "benchmark",
}
_PRIVATE_SUFFIXES = {
    ".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3", ".pem", ".key",
}


def sandbox_mode() -> str:
    mode = os.getenv("SANDBOX_MODE", "docker").strip().lower()
    if mode not in {"docker", "subprocess"}:
        raise ValueError("Set SANDBOX_MODE to docker or subprocess.")
    return mode


def copy_workspace(repo: Path, workspace: Path) -> None:
    """Copy regular files only, omitting local state and benchmark artifacts."""
    private_paths = {
        Path(value).resolve()
        for variable in ("CHROMA_PERSIST_DIR", "INCIDENT_DB_PATH", "HITL_DB_PATH")
        if (value := os.getenv(variable))
    }

    def ignored(directory: str, names: list[str]) -> set[str]:
        excluded = set()
        for name in names:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if (
                name.startswith(".") or name in _EXCLUDED
                or name == "INTERVIEW_CONTEXT.md" or name == "dry_run_test.json"
                or path in private_paths or path.suffix in _PRIVATE_SUFFIXES
                or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))
            ):
                excluded.add(name)
        return excluded

    shutil.copytree(repo, workspace, ignore=ignored, copy_function=shutil.copyfile)
    # The container's unprivileged user needs to create test artifacts here.
    workspace.chmod(0o777)


def _test_path(workspace: Path, test_file: str) -> str:
    return (workspace / test_file).resolve(strict=True).relative_to(workspace.resolve()).as_posix()


def run_in_subprocess(test_dir: str, timeout: int = 30, test_file: str = "test_fix.py") -> tuple[str, bool]:
    workspace = Path(test_dir).resolve()
    target = _test_path(workspace, test_file)
    logging.getLogger(__name__).warning(SUBPROCESS_WARNING)
    env = {
        "PATH": os.defpath,
        "HOME": str(workspace),
        "TMPDIR": str(workspace),
        "PYTHONPATH": os.pathsep.join((str(workspace), str(workspace / "app"))),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    with subprocess.Popen(
        [sys.executable, *_PYTEST_ARGS, "--", target],
        cwd=workspace, env=env, start_new_session=True, text=True, errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return f"Sandbox test run timed out after {timeout}s.", False
    return output, process.returncode == 0


def run_in_docker(test_dir: str, test_file: str = "test_fix.py", timeout: int = 30) -> tuple[str, bool]:
    workspace = Path(test_dir).resolve()
    target = _test_path(workspace, test_file)
    name = f"incident-execution-{uuid4().hex}"
    image = os.getenv("SANDBOX_IMAGE", DOCKER_IMAGE)
    command = [
        "docker", "create", "--init", "--pull", "never", "--name", name,
        "--network", "none", "--ipc", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65532:65532", "--cpus", "1.0", "--memory", "256m",
        "--memory-swap", "256m", "--pids-limit", "64",
        "--mount", f"type=bind,src={workspace},dst=/workspace",
        "--workdir", "/workspace", "--env", "HOME=/workspace", "--env", "TMPDIR=/workspace",
        "--env", "PYTHONPATH=/workspace:/workspace/app", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", "--entrypoint", "python", image,
        *_PYTEST_ARGS, "--", target,
    ]
    try:
        created = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=10)
        if created.returncode:
            return (
                created.stderr + "\nDocker sandbox could not start. "
                "Check Docker access and build the configured SANDBOX_IMAGE.",
                False,
            )
        try:
            result = subprocess.run(
                ["docker", "start", "--attach", name],
                capture_output=True, text=True, errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Docker sandbox test run timed out after {timeout}s.", False
        return result.stdout + result.stderr, result.returncode == 0
    except subprocess.TimeoutExpired:
        return "Docker sandbox creation timed out.", False
    except OSError:
        return "Docker sandbox unavailable. Install and start Docker, then build the sandbox image.", False
    finally:
        _remove_container(name)


def _remove_container(name: str) -> None:
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", name], capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 or "No such container" in result.stderr:
            return
    except FileNotFoundError:
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    logging.getLogger(__name__).warning("Could not confirm cleanup of sandbox container %s.", name)
