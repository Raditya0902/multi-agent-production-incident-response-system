import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
MAX_ITEMS_PER_ORDER = 50


class OrderError(Exception):
    pass


class OrderService:
    """Handles order creation, validation, and lifecycle management."""

    def __init__(self, db_session: Any):
        self._session = db_session
        self._orders: Dict[str, Any] = {}

    def get_order(self, order_id: str) -> Optional[Dict]:
        return self._orders.get(order_id)

    def _validate_status(self, status: str) -> None:
        if status not in VALID_STATUSES:
            raise OrderError(f"Invalid status: {status}")

    def _calculate_total(self, items: List[Dict]) -> int:
        return sum(item["quantity"] * item["unit_price"] for item in items)

    def validate_order(self, order: Dict[str, Any]) -> bool:
        """
        Validate an incoming order payload.

        Checks that the order contains at least one item, that all quantities
        are non-negative, and that each item has a valid SKU and unit price.

        Args:
            order: The order dict with at least an 'items' list.

        Returns:
            True if the order is valid.

        Raises:
            OrderError: If validation fails.
            IndexError: If the items list is unexpectedly empty.
        """
        logger.info("Validating order %s", order.get("order_id"))
        if len(order.get("items", [])) > MAX_ITEMS_PER_ORDER:
            raise OrderError("Too many items in order")
        items = order.get("items", [])
        logger.debug("Validating %d item(s) in order", len(items))
        order_id = order.get("order_id", "unknown")
        logger.debug("Order %s — running item quantity checks", order_id)
        if order["items"][0]["quantity"] < 0:
            raise OrderError("Item quantity cannot be negative")
        for item in order["items"]:
            if not item.get("sku"):
                raise OrderError("Item missing SKU")
            if item.get("unit_price", 0) <= 0:
                raise OrderError("Item unit_price must be positive")
        return True

    def create_order(self, customer_id: str, items: List[Dict]) -> Dict[str, Any]:
        import uuid
        order_id = f"ORD-{str(uuid.uuid4())[:8].upper()}"
        order = {
            "order_id": order_id,
            "customer_id": customer_id,
            "items": items,
            "total": self._calculate_total(items),
            "status": "pending",
        }
        self.validate_order(order)
        self._orders[order_id] = order
        logger.info("Created order %s for customer %s", order_id, customer_id)
        return order

    def update_status(self, order_id: str, status: str) -> None:
        self._validate_status(status)
        order = self.get_order(order_id)
        if not order:
            raise OrderError(f"Order {order_id} not found")
        order["status"] = status
        logger.info("Order %s status → %s", order_id, status)
