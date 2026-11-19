"""Shared trace boundary for running immutable benchmark checkouts.

The adapter may render production trace frames as incident logs. Strip both
test-directory spellings before its source lookups. Private verdicts and raw
pytest output remain evaluator data. Scoring and the provider are unchanged.
"""

from contextlib import contextmanager
from dataclasses import replace
from functools import wraps
from pathlib import PurePosixPath


_TRACE_KEYS = ("frames", "calls", "followed_calls")
_TEST_DIRS = {"test", "tests"}


def _test_location(location):
    directories = PurePosixPath(location[0]).parts[:-1]
    return any(directory.casefold() in _TEST_DIRS for directory in directories)


def _filter_outcomes(outcomes):
    filtered = {}
    for node, outcome in outcomes.items():
        locations = {
            key: [location for location in outcome[key] if not _test_location(location)]
            for key in _TRACE_KEYS if key in outcome
        }
        if any(len(items) != len(outcome[key]) for key, items in locations.items()):
            filtered[node] = {**outcome, **locations}
    return {**outcomes, **filtered} if filtered else outcomes


@contextmanager
def filtered_trace(adapter):
    """Install the same trace-only projection around either frozen adapter."""
    evaluate = adapter.evaluate_revision

    @wraps(evaluate)
    def evaluate_with_filter(*args, **kwargs):
        run = evaluate(*args, **kwargs)
        if not kwargs.get("trace"):
            return run
        outcomes = _filter_outcomes(run.outcomes)
        return replace(run, outcomes=outcomes) if outcomes is not run.outcomes else run

    adapter.evaluate_revision = evaluate_with_filter
    try:
        yield
    finally:
        adapter.evaluate_revision = evaluate


def run_trials(runner, adapter, args, bugs):
    """Run the caller's selected cases through the shared trace boundary."""
    with filtered_trace(adapter):
        return runner.run_all(args, bugs)
