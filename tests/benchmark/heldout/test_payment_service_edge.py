import pytest

from app.payment_service import PaymentError, PaymentProcessor


def test_missing_amount_and_valid_minimum_amount():
    processor = PaymentProcessor(gateway_url="", api_key="")
    with pytest.raises(PaymentError):
        processor.process_payment({"transaction": {}})
    assert processor._transactions == {}
    result = processor.process_payment({"transaction": {"amount": 1}})
    assert result["amount"] == 1
    assert result["status"] == "completed"
