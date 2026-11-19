"""Emit pytest node verdicts and locations without rendering assertion content."""

import json
import os
import re
import sys
from pathlib import Path

import pytest


PREFIX = "INCIDENT_TEST_REPORT="
_outcomes = {}
_calls = {}


def _repo_path(filename):
    workspace = "/workspace/"
    if filename.startswith(workspace):
        return filename[len(workspace):]
    if not filename.startswith("/") and filename.endswith(".py"):
        return filename
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if os.environ.get("INCIDENT_TRACE_SOURCE") != "1":
        yield
        return

    calls = {}
    previous = sys.getprofile()

    def track(frame, event, _arg):
        if event != "call" or frame.f_back is None:
            return
        caller = _repo_path(frame.f_back.f_code.co_filename)
        if caller is None or "tests" not in caller.split("/"):
            return
        source = _repo_path(frame.f_code.co_filename)
        if source and "tests" not in source.split("/") and len(calls) < 16:
            calls[(source, frame.f_code.co_firstlineno, frame.f_code.co_name)] = None

    sys.setprofile(track)
    try:
        yield
    finally:
        sys.setprofile(previous)
        _calls[item.nodeid] = list(calls)


def pytest_runtest_logreport(report):
    if report.when != "call":
        if report.passed:
            return
        _outcomes[report.nodeid] = {"status": "skipped" if report.skipped else "error"}
        return

    if report.passed and hasattr(report, "wasxfail"):
        _outcomes[report.nodeid] = {"status": "error"}
        return
    outcome = {"status": report.outcome}
    if report.failed:
        crash = getattr(report.longrepr, "reprcrash", None)
        message = getattr(crash, "message", "")
        exception = re.match(r"([A-Z][\w.]*)(?:\b|:)", message)
        outcome["exception"] = exception[0] if exception else "TestFailure"
        frames = []
        for entry in getattr(getattr(report.longrepr, "reprtraceback", None), "reprentries", []):
            location = getattr(entry, "reprfileloc", None)
            if location:
                path = Path(location.path)
                if path.is_absolute():
                    if not path.is_relative_to("/workspace"):
                        continue
                    path = path.relative_to("/workspace")
                frames.append([path.as_posix(), location.lineno])
        outcome["frames"] = frames
        outcome["calls"] = _calls.pop(report.nodeid, [])
    _outcomes[report.nodeid] = outcome


def pytest_sessionfinish(session, exitstatus):
    outcomes = _outcomes
    if session.config.option.collectonly:
        outcomes = {item.nodeid: {"status": "collected"} for item in session.items}
    print(PREFIX + json.dumps(outcomes, sort_keys=True), flush=True)
