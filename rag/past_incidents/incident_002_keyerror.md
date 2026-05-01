# Incident: KeyError in payment_service.py
**Date:** 2024-09-03
**Severity:** Critical
**Duration:** 34 minutes
**Affected Users:** 11

## Error
```
KeyError: 'amount'
  File "/app/payment_service.py", line 52, in process_payment
    amount = payload["amount"]
```

## Root Cause
A third-party payment gateway changed its webhook payload schema without notice.
Previously, the `amount` field was at the top level of the payload dict.
After their API update, it was nested under `payload["transaction"]["amount"]`.
Our code accessed the old key directly and crashed when it was absent.

## Fix Applied
Added defensive key access with `.get()` and schema validation:
```python
# Before
amount = payload["amount"]

# After
transaction = payload.get("transaction", {})
amount = transaction.get("amount") or payload.get("amount")
if amount is None:
    raise ValueError(f"Could not find 'amount' in payload. Keys present: {list(payload.keys())}")
```

## Timeline
- 14:22 - Payment failures begin appearing in logs
- 14:31 - Support tickets start coming in
- 14:44 - Root cause identified (schema change from payment gateway)
- 14:56 - Fix deployed

## Prevention
- Use Pydantic models to validate incoming webhook payloads explicitly
- Subscribe to API changelog notifications from all third-party providers
- Add integration tests that replay real webhook payloads
