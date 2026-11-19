import pytest

from app.payment_service import PaymentError, PaymentProcessor


def test_missing_transaction_is_rejected_without_recording_payment():
    processor = PaymentProcessor(gateway_url="", api_key="")
    with pytest.raises(PaymentError):
        processor.process_payment({"order_id": "ORD-1"})
    assert processor._transactions == {}
