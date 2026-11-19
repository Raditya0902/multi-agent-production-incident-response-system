"""Verify the shared boundary before adapters can look up frame source."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from tests.benchmark.real.shared_runner import filtered_trace, run_trials


@dataclass(frozen=True)
class TestReport:
    __test__ = False
    outcomes: dict
    output: str


@pytest.mark.parametrize("key, tail", [
    ("frames", [23]), ("calls", [23, "entry"]), ("followed_calls", [23, "helper"]),
])
def test_trace_filters_both_test_directory_spellings_in_all_location_fields(key, tail):
    private = [
        ["test/secret.py", *tail],
        ["/workspace/package/tests/secret.py", *tail],
        ["nested/Test/secret.py", *tail],
    ]
    public = [["package/contest/service.py", *tail], ["package/service/test.py", *tail]]
    original = TestReport(
        {"sealed-node": {"status": "failed", "exception": "ValueError", key: [*private, *public]}},
        "private evaluator output",
    )
    adapter = SimpleNamespace(evaluate_revision=lambda **options: original)

    with filtered_trace(adapter):
        assert adapter.evaluate_revision() is original
        assert adapter.evaluate_revision(trace=True).outcomes == {
            "sealed-node": {"status": "failed", "exception": "ValueError", key: public},
        }
    assert adapter.evaluate_revision(trace=True) is original
    assert original.outcomes["sealed-node"][key] == [*private, *public]


def test_common_runner_preserves_production_only_report_and_original_adapter():
    trace = TestReport({"node": {"frames": [["pkg/test_data/module.py", 5]]}}, "")
    read = lambda **options: trace
    adapter = SimpleNamespace(evaluate_revision=read)
    args, bugs = object(), [object()]

    def run(selected_args, selected_bugs):
        assert selected_args is args and selected_bugs is bugs
        assert adapter.evaluate_revision is not read
        return adapter.evaluate_revision(trace=True)

    assert run_trials(SimpleNamespace(run_all=run), adapter, args, bugs) is trace
    assert adapter.evaluate_revision is read
