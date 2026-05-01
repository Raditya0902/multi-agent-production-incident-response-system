import os
import logging

logger = logging.getLogger(__name__)

_SEVERITY_ICON = {"P0": "🔴", "P1": "🟠", "P2": "🟡"}
_SEVERITY_COLOR = {"P0": "#e53935", "P1": "#fb8c00", "P2": "#fdd835"}


def is_configured() -> bool:
    return bool(os.getenv("SLACK_BOT_TOKEN") or os.getenv("SLACK_WEBHOOK_URL"))


def notify(state: dict, run_time: float, incident_id: int) -> bool:
    """Send Slack notification for a completed or escalated incident. Returns True if sent."""
    if not is_configured():
        return False
    try:
        if state.get("escalate_to_human"):
            blocks = _build_escalated_blocks(state, run_time, incident_id)
            channel = os.getenv("SLACK_ESCALATION_CHANNEL") or os.getenv("SLACK_INCIDENT_CHANNEL", "#incidents")
        else:
            blocks = _build_resolved_blocks(state, run_time, incident_id)
            channel = os.getenv("SLACK_INCIDENT_CHANNEL", "#incidents")

        severity = state.get("severity", "P2")
        color = _SEVERITY_COLOR.get(severity, "#607d8b")
        _post(blocks, channel, color)
        return True
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------

def _build_resolved_blocks(state: dict, run_time: float, incident_id: int) -> list:
    severity = state.get("severity", "P2")
    icon = _SEVERITY_ICON.get(severity, "⚪")
    customers = state.get("affected_customers") or []
    customer_str = ", ".join(customers) if customers else "—"
    files = state.get("relevant_files") or []
    file_str = ", ".join(f"`{f}`" for f in files) if files else "—"
    root_cause = (state.get("root_cause") or "—")[:300]
    error = (state.get("correlated_error") or "—")[:200]
    retries = state.get("retry_count", 0)
    retry_label = f"{retries} {'retry' if retries == 1 else 'retries'}" if retries else "first attempt"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{icon} {severity} Incident Resolved — #{incident_id}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Error:*\n{error}"},
                {"type": "mrkdwn", "text": f"*Files:*\n{file_str}"},
                {"type": "mrkdwn", "text": f"*Customers Affected:*\n{customer_str} ({len(customers)})"},
                {"type": "mrkdwn", "text": f"*Tests:*\n✅ Passed — {retry_label}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"⏱ {run_time:.1f}s  ·  "
                        f"Saved as incident #{incident_id}  ·  "
                        f"Customer replies drafted  ·  "
                        f"Postmortem generated"
                    ),
                }
            ],
        },
    ]


def _build_escalated_blocks(state: dict, run_time: float, incident_id: int) -> list:
    severity = state.get("severity", "P0")
    icon = _SEVERITY_ICON.get(severity, "🔴")
    customers = state.get("affected_customers") or []
    customer_str = ", ".join(customers) if customers else "—"
    error = (state.get("correlated_error") or "—")[:200]
    max_retries = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
    test_output = (state.get("test_results") or "No test output")[:150]

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🆘 {icon} {severity} Incident Escalated — #{incident_id}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Error:*\n{error}"},
                {"type": "mrkdwn", "text": f"*Customers Waiting:*\n{customer_str} ({len(customers)})"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"⚠️ AI pipeline exhausted *{max_retries} fix attempts* without passing tests.\n"
                    f"*Human engineer review required immediately.*"
                ),
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Last test failure:*\n```{test_output}```"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⏱ {run_time:.1f}s  ·  Incident #{incident_id}  ·  No customer replies sent",
                }
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Transport layer — bot token or webhook
# ---------------------------------------------------------------------------

def _post(blocks: list, channel: str, color: str) -> None:
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    # Plain-text summary used as fallback for push notifications / screen readers
    header_text = blocks[0]["text"]["text"] if blocks else "Incident notification"
    attachment = {"color": color, "blocks": blocks, "fallback": header_text}

    if bot_token:
        from slack_sdk import WebClient
        client = WebClient(token=bot_token)
        client.chat_postMessage(
            channel=channel,
            text=header_text,
            attachments=[attachment],
        )
    elif webhook_url:
        from slack_sdk.webhook import WebhookClient
        client = WebhookClient(webhook_url)
        response = client.send(
            text=header_text,
            attachments=[attachment],
        )
        if response.status_code != 200:
            raise RuntimeError(f"Slack webhook returned {response.status_code}: {response.body}")
    else:
        raise RuntimeError("No Slack credentials configured.")
