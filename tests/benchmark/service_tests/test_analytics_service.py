from unittest.mock import Mock

from app.analytics_service import AnalyticsService


def test_empty_period_returns_zero_conversion():
    store = Mock(fetch_sessions=Mock(return_value=[]), fetch_orders=Mock(return_value=[]))
    report = AnalyticsService(store).compute_conversion_rate("empty", "2024-01-01", "2024-01-02")
    assert report["total_sessions"] == report["successful_orders"] == 0
    assert report["conversion_rate_pct"] == 0.0
