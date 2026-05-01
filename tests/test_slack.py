import pytest
from notifications.slack import (
    is_configured,
    notify,
    _build_resolved_blocks,
    _build_escalated_blocks,
)

RESOLVED_STATE = {
    "severity": "P1",
    "severity_reason": "Core feature broken for 2 users.",
    "correlated_error": "IndexError: list index out of range in data_processing.py:42",
    "affected_customers": ["Alice Johnson", "Bob Martinez"],
    "relevant_files": ["data_processing.py"],
    "root_cause": "Missing bounds check before list indexing.",
    "code_patch": "===FILE===\ndata_processing.py\n===FIXED===\nreturn items[index] if index < len(items) else None",
    "test_results": "4 passed in 0.01s",
    "tests_passed": True,
    "retry_count": 1,
    "escalate_to_human": False,
    "status": "complete",
}

ESCALATED_STATE = {
    **RESOLVED_STATE,
    "severity": "P0",
    "tests_passed": False,
    "escalate_to_human": True,
    "status": "escalated",
    "test_results": "FAILED: AssertionError at test_fix.py:12",
}


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_not_configured_when_no_env(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert is_configured() is False


def test_configured_with_bot_token(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert is_configured() is True


def test_configured_with_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    assert is_configured() is True


# ---------------------------------------------------------------------------
# Block builders — pure functions, no network
# ---------------------------------------------------------------------------

def test_resolved_blocks_header():
    blocks = _build_resolved_blocks(RESOLVED_STATE, 30.0, 1)
    header = blocks[0]
    assert header["type"] == "header"
    assert "Resolved" in header["text"]["text"]
    assert "P1" in header["text"]["text"]
    assert "#1" in header["text"]["text"]


def test_resolved_blocks_severity_icon():
    blocks = _build_resolved_blocks({**RESOLVED_STATE, "severity": "P0"}, 10.0, 5)
    assert "🔴" in blocks[0]["text"]["text"]

    blocks = _build_resolved_blocks({**RESOLVED_STATE, "severity": "P1"}, 10.0, 5)
    assert "🟠" in blocks[0]["text"]["text"]

    blocks = _build_resolved_blocks({**RESOLVED_STATE, "severity": "P2"}, 10.0, 5)
    assert "🟡" in blocks[0]["text"]["text"]


def test_resolved_blocks_customer_names():
    blocks = _build_resolved_blocks(RESOLVED_STATE, 30.0, 1)
    section_text = str(blocks)
    assert "Alice Johnson" in section_text
    assert "Bob Martinez" in section_text


def test_resolved_blocks_root_cause():
    blocks = _build_resolved_blocks(RESOLVED_STATE, 30.0, 1)
    root_cause_block = next(b for b in blocks if b.get("type") == "section" and "Root Cause" in str(b))
    assert "bounds check" in root_cause_block["text"]["text"]


def test_resolved_blocks_has_context():
    blocks = _build_resolved_blocks(RESOLVED_STATE, 47.3, 7)
    context = next(b for b in blocks if b["type"] == "context")
    text = context["elements"][0]["text"]
    assert "47.3s" in text
    assert "#7" in text


def test_escalated_blocks_header():
    blocks = _build_escalated_blocks(ESCALATED_STATE, 90.0, 2)
    header = blocks[0]
    assert header["type"] == "header"
    assert "Escalated" in header["text"]["text"]
    assert "P0" in header["text"]["text"]


def test_escalated_blocks_human_required():
    blocks = _build_escalated_blocks(ESCALATED_STATE, 90.0, 2)
    body_text = str(blocks)
    assert "Human engineer" in body_text or "human engineer" in body_text.lower()


def test_escalated_blocks_test_failure():
    blocks = _build_escalated_blocks(ESCALATED_STATE, 90.0, 2)
    body_text = str(blocks)
    assert "AssertionError" in body_text


def test_resolved_blocks_truncates_long_error():
    long_error = "E" * 500
    state = {**RESOLVED_STATE, "correlated_error": long_error}
    blocks = _build_resolved_blocks(state, 10.0, 1)
    body_text = str(blocks)
    # Should be truncated (200 chars max in error field)
    assert len(long_error) > 200
    assert long_error not in body_text


def test_resolved_blocks_handles_no_customers():
    state = {**RESOLVED_STATE, "affected_customers": []}
    blocks = _build_resolved_blocks(state, 10.0, 1)
    assert "—" in str(blocks)


def test_resolved_blocks_handles_no_files():
    state = {**RESOLVED_STATE, "relevant_files": []}
    blocks = _build_resolved_blocks(state, 10.0, 1)
    assert "—" in str(blocks)


# ---------------------------------------------------------------------------
# notify() — mock the transport layer
# ---------------------------------------------------------------------------

def test_notify_skips_when_not_configured(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    result = notify(RESOLVED_STATE, 30.0, 1)
    assert result is False


def test_notify_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("SLACK_INCIDENT_CHANNEL", "#test-incidents")
    posted = []

    def fake_post(blocks, channel, color):
        posted.append({"blocks": blocks, "channel": channel, "color": color})

    monkeypatch.setattr("notifications.slack._post", fake_post)
    result = notify(RESOLVED_STATE, 30.0, 1)
    assert result is True
    assert len(posted) == 1
    assert posted[0]["channel"] == "#test-incidents"


def test_notify_uses_escalation_channel_for_escalated(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("SLACK_INCIDENT_CHANNEL", "#incidents")
    monkeypatch.setenv("SLACK_ESCALATION_CHANNEL", "#on-call")
    posted = []

    def fake_post(blocks, channel, color):
        posted.append(channel)

    monkeypatch.setattr("notifications.slack._post", fake_post)
    notify(ESCALATED_STATE, 90.0, 2)
    assert posted[0] == "#on-call"


def test_notify_falls_back_to_incident_channel_when_escalation_channel_not_set(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setenv("SLACK_INCIDENT_CHANNEL", "#incidents")
    monkeypatch.delenv("SLACK_ESCALATION_CHANNEL", raising=False)
    posted = []

    def fake_post(blocks, channel, color):
        posted.append(channel)

    monkeypatch.setattr("notifications.slack._post", fake_post)
    notify(ESCALATED_STATE, 90.0, 2)
    assert posted[0] == "#incidents"


def test_notify_returns_false_on_exception(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")

    def bad_post(blocks, channel, color):
        raise ConnectionError("network down")

    monkeypatch.setattr("notifications.slack._post", bad_post)
    result = notify(RESOLVED_STATE, 30.0, 1)
    assert result is False


def test_notify_p0_color(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    posted = []

    def fake_post(blocks, channel, color):
        posted.append(color)

    monkeypatch.setattr("notifications.slack._post", fake_post)
    notify({**RESOLVED_STATE, "severity": "P0"}, 10.0, 1)
    assert posted[0] == "#e53935"


def test_notify_p1_color(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    posted = []

    def fake_post(blocks, channel, color):
        posted.append(color)

    monkeypatch.setattr("notifications.slack._post", fake_post)
    notify(RESOLVED_STATE, 10.0, 1)  # P1
    assert posted[0] == "#fb8c00"
