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
_followed_calls = {}


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
    followed = {}
    active = {}
    previous = sys.getprofile()

    def track(frame, event, _arg):
        if event == "return":
            active.pop(id(frame), None)
            return
        if event != "call" or frame.f_back is None:
            return
        caller = _repo_path(frame.f_back.f_code.co_filename)
        source = _repo_path(frame.f_code.co_filename)
        if not source or {"test", "tests"} & set(source.split("/")):
            return
        entry = caller and {"test", "tests"} & set(caller.split("/"))
        parent = active.get(id(frame.f_back))
        if not entry and parent is None:
            return
        location = (source, frame.f_code.co_firstlineno, frame.f_code.co_name)
        if entry:
            active[id(frame)] = (0, source)
            if len(calls) < 16:
                calls[location] = None
            return
        depth, parent_source = parent
        if depth < 6:
            active[id(frame)] = (depth + 1, source)
            if source != parent_source and len(followed) < 32:
                followed.setdefault(location, depth + 1)

    sys.setprofile(track)
    try:
        yield
    finally:
        sys.setprofile(previous)
        _calls[item.nodeid] = list(calls)
        # Keep observed cross-file calls in deterministic, shallow-first order.
        _followed_calls[item.nodeid] = [
            location for location, _ in sorted(followed.items(), key=lambda item: item[1])
        ]


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
        if report.nodeid in _followed_calls:
            outcome["followed_calls"] = _followed_calls.pop(report.nodeid)
    _outcomes[report.nodeid] = outcome


def pytest_sessionfinish(session, exitstatus):
    outcomes = _outcomes
    if session.config.option.collectonly:
        outcomes = {item.nodeid: {"status": "collected"} for item in session.items}
    print(PREFIX + json.dumps(outcomes, sort_keys=True), flush=True)
