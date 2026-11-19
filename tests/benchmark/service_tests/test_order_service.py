import pytest

from app.order_service import OrderError, OrderService


def test_empty_order_is_rejected_as_validation_error():
    with pytest.raises(OrderError):
        OrderService(None).validate_order({"items": []})
