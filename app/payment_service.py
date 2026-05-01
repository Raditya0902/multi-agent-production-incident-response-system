import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD"}
MIN_AMOUNT_CENTS = 1
MAX_AMOUNT_CENTS = 10_000_000
PAYMENT_TIMEOUT_SECONDS = 30


class PaymentError(Exception):
    pass


class InsufficientFundsError(PaymentError):
    pass


class PaymentProcessor:
    """Handles payment processing and transaction management."""

    def __init__(self, gateway_url: str, api_key: str):
        self.gateway_url = gateway_url
        self.api_key = api_key
        self._transactions: Dict[str, Any] = {}

    def _generate_transaction_id(self) -> str:
        return str(uuid.uuid4())

    def _validate_currency(self, currency: str) -> None:
        if currency not in SUPPORTED_CURRENCIES:
            raise PaymentError(f"Unsupported currency: {currency}")

    def _validate_amount(self, amount: int) -> None:
        if not isinstance(amount, int):
            raise PaymentError("Amount must be an integer (cents)")
        if amount < MIN_AMOUNT_CENTS:
            raise PaymentError(f"Amount below minimum: {amount}")
        if amount > MAX_AMOUNT_CENTS:
            raise PaymentError(f"Amount exceeds maximum: {amount}")

    def _record_transaction(
        self,
        transaction_id: str,
        amount: int,
        currency: str,
        order_id: str,
        status: str,
    ) -> None:
        self._transactions[transaction_id] = {
            "id": transaction_id,
            "amount": amount,
            "currency": currency,
            "order_id": order_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_transaction(self, transaction_id: str) -> Optional[Dict]:
        return self._transactions.get(transaction_id)

    def refund(self, transaction_id: str) -> bool:
        txn = self.get_transaction(transaction_id)
        if not txn:
            return False
        txn["status"] = "refunded"
        logger.info("Refunded transaction %s", transaction_id)
        return True

    def process_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a payment from the given payload.

        Expected payload structure:
            {"transaction": {"amount": <int_cents>, "currency": <str>}, "order_id": <str>}
        """
        order_id = payload.get("order_id", "unknown")
        currency = payload.get("currency", "USD")
        self._validate_currency(currency)
        transaction_id = self._generate_transaction_id()
        logger.info("Processing payment for order %s (txn: %s)", order_id, transaction_id)
        logger.debug("Payload keys received: %s", list(payload.keys()))
        logger.debug("Validating transaction block in payload")
        amount = payload["transaction"]["amount"]
        self._validate_amount(amount)
        self._record_transaction(transaction_id, amount, currency, order_id, "pending")
        logger.info("Payment authorised: txn=%s amount=%d %s", transaction_id, amount, currency)
        self._transactions[transaction_id]["status"] = "completed"
        return {
            "transaction_id": transaction_id,
            "order_id": order_id,
            "amount": amount,
            "currency": currency,
            "status": "completed",
        }


def process_payment(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Module-level entry point used by the API layer."""
    processor = PaymentProcessor(
        gateway_url="https://gateway.internal",
        api_key="internal",
    )
    return processor.process_payment(payload)
