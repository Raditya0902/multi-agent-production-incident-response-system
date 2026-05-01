import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REPORT_FORMATS = ["json", "csv", "html"]
DEFAULT_LOOKBACK_DAYS = 7


class AnalyticsError(Exception):
    pass


class ReportStore:
    """Thin abstraction over the analytics data warehouse."""

    def __init__(self, db_session: Any):
        self._session = db_session

    def fetch_sessions(self, start: datetime, end: datetime) -> List[Dict]:
        return self._session.query("sessions").between(start, end).all()

    def fetch_orders(self, start: datetime, end: datetime) -> List[Dict]:
        return self._session.query("orders").between(start, end).all()

    def fetch_events(self, event_type: str, start: datetime, end: datetime) -> List[Dict]:
        return (
            self._session.query("events")
            .filter(type=event_type)
            .between(start, end)
            .all()
        )


class AnalyticsService:
    """Generates business intelligence reports from raw event data."""

    def __init__(self, store: ReportStore):
        self.store = store

    def _parse_date_range(
        self, start_str: str, end_str: str
    ) -> Tuple[datetime, datetime]:
        fmt = "%Y-%m-%d"
        return datetime.strptime(start_str, fmt), datetime.strptime(end_str, fmt)

    def _default_range(self) -> Tuple[datetime, datetime]:
        end = datetime.utcnow()
        start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        return start, end

    def get_session_count(self, start: datetime, end: datetime) -> int:
        return len(self.store.fetch_sessions(start, end))

    def get_order_count(self, start: datetime, end: datetime) -> int:
        return len(self.store.fetch_orders(start, end))

    def compute_conversion_rate(
        self,
        report_id: str,
        start_str: Optional[str] = None,
        end_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute the order conversion rate for the given time range.

        Conversion rate = successful_orders / total_sessions * 100.
        Raises ZeroDivisionError if no sessions were recorded in the period.

        Args:
            report_id: Identifier for this report run.
            start_str: ISO date string (YYYY-MM-DD). Defaults to 7 days ago.
            end_str:   ISO date string (YYYY-MM-DD). Defaults to now.
        """
        logger.info("Generating conversion report %s", report_id)
        if start_str and end_str:
            start, end = self._parse_date_range(start_str, end_str)
        else:
            start, end = self._default_range()
        successful_orders = self.get_order_count(start, end)
        total_sessions = self.get_session_count(start, end)
        logger.debug("orders=%d sessions=%d", successful_orders, total_sessions)
        logger.info(
            "Report %s: %d orders across %d sessions",
            report_id,
            successful_orders,
            total_sessions,
        )
        logger.debug("Computing conversion rate for report %s", report_id)
        rate = successful_orders / total_sessions
        return {
            "report_id": report_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_sessions": total_sessions,
            "successful_orders": successful_orders,
            "conversion_rate_pct": round(rate * 100, 2),
        }

    def generate_weekly_report(self, report_id: str) -> Dict[str, Any]:
        end = datetime.utcnow()
        start = end - timedelta(days=7)
        return self.compute_conversion_rate(
            report_id,
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )

    def list_top_products(
        self, start: datetime, end: datetime, limit: int = 10
    ) -> List[Dict]:
        orders = self.store.fetch_orders(start, end)
        counts: Dict[str, int] = {}
        for order in orders:
            for item in order.get("items", []):
                sku = item.get("sku", "unknown")
                counts[sku] = counts.get(sku, 0) + item.get("quantity", 0)
        sorted_products = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"sku": sku, "units_sold": qty} for sku, qty in sorted_products[:limit]]
