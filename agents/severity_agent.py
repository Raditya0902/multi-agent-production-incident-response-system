import re
import json
from langchain_core.messages import SystemMessage, HumanMessage

from agents import llm
from agents.state import IncidentState

SYSTEM_PROMPT = """You are an incident severity classifier. Assign a priority level based on the correlated error and the number and nature of affected customers.

Severity definitions:
- P0 (Critical): Payment/billing failures, data loss, complete feature outage, 5+ customers affected, or keywords like "charged", "lost data", "all users down"
- P1 (High): Core feature broken for multiple users, crashes on key user flows, 3-4 customers affected, or customer urgency signals like "deadline", "urgent", "broken"
- P2 (Medium): Non-critical feature degraded, 1-2 customers affected, workaround likely exists

Respond ONLY in this exact JSON format (no markdown, no extra text):
{
  "severity": "P0",
  "severity_reason": "One sentence explaining why this severity was chosen."
}"""


def _parse_json(text: str) -> dict:
    text = re.sub(r"```json?\s*|\s*```", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def severity_agent(state: IncidentState) -> dict:
    customer_count = len(state.get("affected_customers", []))
    human_content = (
        f"Correlated Error: {state['correlated_error']}\n"
        f"Affected Customers ({customer_count}): {', '.join(state.get('affected_customers', []))}\n"
        f"Raw Logs Excerpt:\n{state['raw_logs'][:800]}"
    )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    try:
        parsed = _parse_json(response.content)
        severity = parsed.get("severity", "P2").upper()
        if severity not in ("P0", "P1", "P2"):
            severity = "P2"
        reason = parsed.get("severity_reason", "")
    except Exception:
        # Fallback: derive from customer count alone
        severity = "P0" if customer_count >= 5 else "P1" if customer_count >= 3 else "P2"
        reason = f"Fallback classification based on {customer_count} affected customer(s)."

    return {
        "severity": severity,
        "severity_reason": reason,
        "status": "severity_classified",
    }
