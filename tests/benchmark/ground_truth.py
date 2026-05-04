"""
Ground truth definitions for all 7 test scenarios in test_cases.txt.
Each entry maps a buggy file to its known error characteristics and
the pattern that a correct fix must contain.
"""

GROUND_TRUTH = {
    "data_processing.py": {
        "bug_description": "IndexError at line 42 — missing bounds check before list indexing",
        "original_line": "result = items[index]",
        # Accept any valid bounds-check approach: explicit compare, try/except, or slice guard
        "correct_fix_pattern": ["len(items)", "index < len", "except IndexError", "try:"],
        "error_type": "IndexError",
        "severity": "P1",
    },
    "payment_service.py": {
        "bug_description": "KeyError at line 87 — missing dict key check on 'transaction'",
        "original_line": 'amount = payload["transaction"]["amount"]',
        "correct_fix_pattern": ['.get("amount")', ".get('amount')", "get("],
        "error_type": "KeyError",
        "severity": "P0",
    },
    "database_service.py": {
        "bug_description": "TimeoutError at line 134 — no connection pool limit, pool exhausted",
        "original_line": "conn = pool.getconn()",
        "correct_fix_pattern": ["timeout", "pool_size", "max_overflow", "connect_timeout"],
        "error_type": "TimeoutError",
        "severity": "P1",
    },
    "notification_service.py": {
        "bug_description": "AttributeError at line 78 — accessing attribute on None user object",
        "original_line": "email = user.email",
        # Any None-guard pattern is correct: explicit is-None check, truthiness, or is-not-None guard
        "correct_fix_pattern": ["is None", "is not None", "if not user", "if user"],
        "error_type": "AttributeError",
        "severity": "P2",
    },
    "api_gateway.py": {
        "bug_description": "Mass outage — multiple error types, unhandled exception in route_request",
        "original_line": "handler = routes[request.path]",
        "correct_fix_pattern": [".get(", "KeyError", "except"],
        "error_type": "KeyError",
        "severity": "P0",
    },
    "analytics_service.py": {
        "bug_description": "ZeroDivisionError at line 91 — no zero-denominator check in conversion rate",
        # Log uses total_sessions; accept either name plus any zero-guard idiom
        "original_line": "rate = successful_orders / total_sessions",
        "correct_fix_pattern": ["total_sessions", "== 0", "!= 0", "if not total", "or 0"],
        "error_type": "ZeroDivisionError",
        "severity": "P2",
    },
    "order_service.py": {
        "bug_description": "ValueError at line 55 — missing validation for order total",
        "original_line": "total = sum(item['price'] for item in order['items'])",
        "correct_fix_pattern": ["items", "if not order", "len(", "empty"],
        "error_type": "ValueError",
        "severity": "P1",
    },
}
