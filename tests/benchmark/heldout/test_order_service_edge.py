import pytest

from app.order_service import OrderError, OrderService


def test_rejects_negative_quantity_beyond_first_item():
    service = OrderService(None)
    valid = {"sku": "A", "quantity": 1, "unit_price": 5}
    invalid = {"sku": "B", "quantity": -1, "unit_price": 3}
    assert service.validate_order({"items": [valid]}) is True
    with pytest.raises(OrderError):
        service.validate_order({"items": [valid, invalid]})
