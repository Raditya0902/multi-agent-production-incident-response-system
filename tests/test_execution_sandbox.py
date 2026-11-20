import importlib
import os
from pathlib import Path
import subprocess

import pytest

from agents.state import create_initial_state
from sandbox.runner import DOCKER_IMAGE, copy_workspace, run_in_docker, sandbox_mode

execution = importlib.import_module("agents.execution_agent")


@pytest.fixture
def service(tmp_path, monkeypatch):
    repo = tmp_path / "host-repo"
    source = repo / "app" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text("def value():\n    return 0\n")
    tests = repo / "tests"
    tests.mkdir()
    (repo / ".env").write_text("DEMO_PRIVATE_VALUE=host-only\n")
    (repo / "shortcut").symlink_to(tmp_path / "host-canary")
    (tmp_path / "host-canary").write_text("unchanged")
    monkeypatch.setattr(execution, "_PROJECT_ROOT", str(repo))
    return repo, source, tests / "test_service.py"


def run_patch(fixed):
    state = create_initial_state([], "")
    state["code_patch"] = (
        "===FILE===\napp/service.py\n===ORIGINAL===\nreturn 0\n"
        f"===FIXED===\n{fixed}\n===EXPLANATION===\nSandbox fixture."
    )
    return execution.execution_agent(state)


def test_subprocess_uses_a_fresh_repo_copy(service, monkeypatch, caplog):
    repo, source, test_file = service
    monkeypatch.setenv("SANDBOX_MODE", "subprocess")
    monkeypatch.setenv("DEMO_PRIVATE_VALUE", "host-only")
    test_file.write_text(
        "import os\nfrom pathlib import Path\nfrom app.service import value\n"
        "def test_candidate():\n"
        "    assert value() == 42\n"
        "    assert not Path('.env').exists()\n"
        "    assert 'DEMO_PRIVATE_VALUE' not in os.environ\n"
        "    assert not Path('scratch.txt').exists()\n"
        "    Path('scratch.txt').write_text('temporary')\n"
    )
    for _ in range(2):
        result = run_patch("return 42")
        assert result["tests_passed"], result["test_results"]
        assert result["used_real_tests"]
    assert "Subprocess sandbox active" in caplog.text
    assert source.read_text() == "def value():\n    return 0\n"
    assert not (repo / "scratch.txt").exists()


def test_subprocess_timeout(tmp_path):
    (tmp_path / "test_fix.py").write_text("import time\ndef test_slow():\n    time.sleep(10)\n")
    output, passed = execution.run_in_subprocess(str(tmp_path), timeout=1)
    assert not passed and "timed out" in output


def test_docker_is_default_and_never_downgrades(service, monkeypatch):
    _, _, test_file = service
    test_file.write_text("def test_candidate():\n    pass\n")
    monkeypatch.delenv("SANDBOX_MODE", raising=False)
    assert sandbox_mode() == "docker"

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("Docker CLI unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)
    monkeypatch.setattr(execution, "run_in_subprocess", lambda *args, **kwargs: pytest.fail("downgraded"))
    result = run_patch("return 42")
    assert not result["tests_passed"]
    assert "Docker sandbox unavailable" in result["test_results"]


@pytest.fixture
def sandbox_image():
    image = os.getenv("SANDBOX_IMAGE", DOCKER_IMAGE)
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Local Docker sandbox image unavailable")
    if result.returncode:
        pytest.skip("Build the local Docker sandbox image to run filesystem boundary tests")


def test_docker_keeps_generated_code_inside_workspace(service, sandbox_image, monkeypatch):
    repo, source, test_file = service
    canary = repo.parent / "host-canary"
    monkeypatch.setenv("SANDBOX_MODE", "docker")
    monkeypatch.setenv("DEMO_PRIVATE_VALUE", "host-only")
    test_file.write_text(
        "from app.service import value\n"
        "def test_candidate():\n"
        "    assert value() == 42\n"
    )
    result = run_patch(
        "from pathlib import Path\n"
        "    import os\n"
        "    assert os.getuid() != 0\n"
        "    import socket\n"
        "    import errno\n"
        "    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:\n"
        "        try:\n"
        "            probe.connect(('192.0.2.1', 9))\n"
        "        except OSError as error:\n"
        "            assert error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)\n"
        "        else:\n"
        "            raise AssertionError('container has an external network route')\n"
        "    assert 'DEMO_PRIVATE_VALUE' not in os.environ\n"
        "    mounts = {line.split()[4]: line.split()[5].split(',')\n"
        "              for line in Path('/proc/self/mountinfo').read_text().splitlines()}\n"
        "    assert 'ro' in mounts['/'] and 'rw' in mounts['/workspace']\n"
        "    assert not Path('.env').exists()\n"
        "    assert not Path('shortcut').is_symlink()\n"
        "    for outside in (Path('/etc/incident-canary'), Path('../incident-canary'),"
        f" Path({str(canary)!r})):\n"
        "        try:\n"
        "            outside.write_text('changed')\n"
        "        except OSError:\n"
        "            pass\n"
        "        else:\n"
        "            raise AssertionError('outside write succeeded')\n"
        f"    assert not Path({str(canary)!r}).exists()\n"
        "    try:\n"
        f"        Path({str(canary)!r}).read_text()\n"
        "    except OSError:\n"
        "        pass\n"
        "    else:\n"
        "        raise AssertionError('outside read succeeded')\n"
        "    Path('scratch.txt').write_text('temporary')\n"
        "    return 42"
    )
    assert result["tests_passed"], result["test_results"]
    assert source.read_text() == "def value():\n    return 0\n"
    assert canary.read_text() == "unchanged"
    assert not run_patch("return 7")["tests_passed"]
    assert not (repo / "scratch.txt").exists()


def test_docker_timeout_removes_container(service, sandbox_image):
    repo, _, test_file = service
    test_file.write_text("import time\ndef test_slow():\n    time.sleep(10)\n")
    workspace = repo.parent / "workspace"
    copy_workspace(repo, workspace)
    output, passed = run_in_docker(str(workspace), "tests/test_service.py", timeout=3)
    assert not passed and "timed out" in output
    running = subprocess.check_output(
        ["docker", "ps", "-q", "--filter", f"volume={workspace.resolve()}"], text=True,
    )
    assert not running.strip()
