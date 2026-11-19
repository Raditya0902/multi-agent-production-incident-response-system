from unittest.mock import Mock

from app.analytics_service import AnalyticsService


def test_nonzero_period_keeps_counts_and_rounding():
    store = Mock(
        fetch_sessions=Mock(return_value=[{}, {}, {}]),
        fetch_orders=Mock(return_value=[{}]),
    )
    report = AnalyticsService(store).compute_conversion_rate("active", "2024-01-01", "2024-01-02")
    assert report["report_id"] == "active"
    assert report["total_sessions"] == 3
    assert report["successful_orders"] == 1
    assert report["conversion_rate_pct"] == 33.33
