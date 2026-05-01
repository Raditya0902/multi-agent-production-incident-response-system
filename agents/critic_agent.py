from langchain_core.messages import SystemMessage, HumanMessage

from agents import llm
from agents.state import IncidentState

SYSTEM_PROMPT = """You are a code review critic analyzing a failed bug fix attempt.
You will receive the root cause diagnosis, the code patch that was attempted, and the pytest failure output.

Provide concise, actionable feedback for the next fix attempt.
Identify EXACTLY what went wrong and what the next attempt must do differently.

Respond in this exact format:
WHAT FAILED: (one sentence)
WHY IT FAILED: (one or two sentences)
NEXT ATTEMPT MUST:
- (specific instruction 1)
- (specific instruction 2)
- (specific instruction 3)"""


def critic_agent(state: IncidentState) -> dict:
    human_content = (
        f"Root Cause:\n{state['root_cause']}\n\n"
        f"Code Patch Attempted:\n{state['code_patch']}\n\n"
        f"Test Failure Output:\n```\n{state['test_results']}\n```\n"
        f"Retry Attempt: {state.get('retry_count', 1)}"
    )

    if state.get("critic_feedback"):
        human_content += (
            f"\n\nPrevious critic feedback (do not repeat this advice):\n{state['critic_feedback']}"
        )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    return {
        "critic_feedback": response.content.strip(),
        "status": "critique_complete",
    }
