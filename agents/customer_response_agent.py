import re
from langchain_core.messages import SystemMessage, HumanMessage

from agents import llm
from agents.state import IncidentState

SYSTEM_PROMPT = """You are a customer support specialist drafting personalized apology messages.
For each customer listed, write a brief, empathetic reply.

Rules:
- Address each customer by first name
- Do NOT mention technical details (no stack traces, function names, or file names)
- Explain the issue in plain English (1 sentence)
- Confirm the status (resolved or being escalated)
- Keep each message under 80 words
- Be warm and professional

Separate each reply with exactly this delimiter on its own line:
---NEXT---"""


def customer_response_agent(state: IncidentState) -> dict:
    customers = state.get("affected_customers", [])
    if not customers:
        return {"customer_replies": [], "status": "responses_drafted"}

    fix_status = (
        "has been resolved"
        if state.get("tests_passed")
        else "is being escalated to our senior engineering team for immediate attention"
    )

    # Simplify the root cause to non-technical language via one LLM call
    # that also produces all customer replies — avoids per-customer API calls
    customer_list = "\n".join(f"- {name}" for name in customers)

    human_content = (
        f"Root Cause (translate to plain English for customers): {state['root_cause']}\n\n"
        f"Fix Status: The issue {fix_status}.\n\n"
        f"Write a personalized reply for each of these customers:\n{customer_list}\n\n"
        f"Use ---NEXT--- between each reply."
    )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    raw = response.content.strip()
    parts = re.split(r"\n---NEXT---\n?", raw)
    replies = [p.strip() for p in parts if p.strip()]

    # Label each reply with the customer name
    labeled_replies = []
    for i, reply in enumerate(replies):
        name = customers[i] if i < len(customers) else f"Customer {i+1}"
        labeled_replies.append(f"To: {name}\n\n{reply}")

    return {
        "customer_replies": labeled_replies,
        "status": "responses_drafted",
    }
