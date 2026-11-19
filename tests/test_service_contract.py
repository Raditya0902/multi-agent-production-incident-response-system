from agents.service_contract import source_contracts
from agents.source_context import SourceWindow
from tests.benchmark.feedback import behavior_counts, service_counts


def test_contract_uses_nearest_function_and_excludes_nested_behavior():
    source = (
        'def owner(value: int) -> dict:\n'
        '    def helper():\n'
        '        raise RuntimeError("other scope")\n'
        '    if value < 0:\n'
        '        raise ValueError("negative")\n'
        '    return {"value": value}\n'
    )
    window = SourceWindow("module.py", 1, 6, source, 5)
    excerpt = source_contracts([window], lambda _: source)
    assert "owner(value: int) -> dict" in excerpt
    assert "raise ValueError('negative')" in excerpt
    assert "return {'value': value}" in excerpt
    assert "other scope" not in excerpt


def test_aggregate_feedback_contains_counts_only():
    assert service_counts("secret assertion\n1 failed, 3 passed in 0.1s") == (
        "Service checks: 3 passed, 1 failed."
    )
    assert behavior_counts(
        {"hidden-regression": "failed", "hidden-control": "passed"},
        ("hidden-regression",), ("hidden-control",),
    ) == "Regression checks: 0 passed, 1 failed. Previously passing checks: 1 passed, 0 failed."
