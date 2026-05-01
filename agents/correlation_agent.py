import re
import json
from langchain_core.messages import SystemMessage, HumanMessage

from agents import llm
from agents.state import IncidentState

SYSTEM_PROMPT = """You are an incident correlation specialist.
Analyze the customer complaints and error logs provided.
Extract:
1. A concise error summary (1-2 sentences) linking the complaints to the specific error
2. A list of affected customer FULL NAMES — extract these from the complaint messages only, not from the logs.
   Use the person's actual name (e.g. "Alice Johnson"), never a user ID (e.g. never "user_alice_001").
   If a complaint is signed or addressed to a name, use that name.

Respond ONLY in this exact JSON format (no markdown, no extra text):
{
  "correlated_error": "...",
  "affected_customers": ["Full Name 1", "Full Name 2"]
}"""


def _parse_json(text: str) -> dict:
    # Strip markdown code fences if present
    text = re.sub(r"```json?\s*|\s*```", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def correlation_agent(state: IncidentState) -> dict:
    complaints_text = "\n".join(f"- {c}" for c in state["raw_complaints"])
    human_content = (
        f"Customer Complaints:\n{complaints_text}\n\n"
        f"Error Logs:\n```\n{state['raw_logs']}\n```"
    )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    parsed = _parse_json(response.content)

    return {
        "correlated_error": parsed.get("correlated_error", ""),
        "affected_customers": parsed.get("affected_customers", []),
        "status": "correlation_complete",
    }
