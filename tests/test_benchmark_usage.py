from datetime import datetime, timezone
from decimal import Decimal

import pytest

from agents import benchmark_usage


def test_budget_reserves_before_dispatch_and_counts_across_invocations(tmp_path):
    ledger = tmp_path / "usage.sqlite3"
    cap = Decimal("0.321")
    first = benchmark_usage.DeepSeekUsage(ledger, cap)
    ticket = first.reserve(4096)

    second = benchmark_usage.DeepSeekUsage(ledger, cap)
    with pytest.raises(benchmark_usage.BenchmarkStop, match="before the next request"):
        second.reserve(4096)
    first.settle(ticket, {"prompt_tokens": 1_000, "completion_tokens": 200}, {})
    assert first.snapshot()["output_tokens"] == 200
    assert second.snapshot()["request_count"] == 0
    assert second.snapshot(cumulative=True)["request_count"] == 1
    assert second.reserve(4096)
    assert second.snapshot(cumulative=True)["unsettled_requests"] == 1


def test_cost_uses_cached_input_and_reasoning_is_part_of_output(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_usage, "_peak_at", lambda timestamp: False)
    meter = benchmark_usage.DeepSeekUsage(tmp_path / "usage.sqlite3", Decimal("2.50"))
    request = meter.reserve(4096)
    meter.settle(request, {
        "prompt_tokens": 1_000, "completion_tokens": 200, "prompt_cache_hit_tokens": 500,
        "completion_tokens_details": {"reasoning_tokens": 100},
    }, {})
    usage = meter.snapshot()
    assert usage["cached_input_tokens"] == 500
    assert usage["reasoning_tokens"] == 100
    assert usage["output_tokens"] == 200
    assert usage["estimated_cost_usd"] == 0.0001965
    assert usage["guarded_spend_usd"] == 0.000393


def test_peak_schedule():
    assert benchmark_usage._peak_at(datetime(2026, 11, 19, 2, tzinfo=timezone.utc))
    assert not benchmark_usage._peak_at(datetime(2026, 11, 19, 5, tzinfo=timezone.utc))
    assert not benchmark_usage._peak_at(datetime(2026, 11, 21, 2, tzinfo=timezone.utc))
