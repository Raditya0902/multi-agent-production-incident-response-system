import re
import json
from langchain_core.messages import SystemMessage, HumanMessage

from agents import llm
from agents.state import IncidentState
from rag.vectorstore import retrieve_context

SYSTEM_PROMPT = """You are a senior software engineer performing root cause analysis.
You are given:
1. The correlated error summary
2. The raw error logs / stack trace
3. Relevant past incidents from the knowledge base

Diagnose the root cause. Be specific about the file, function, and line number if visible.
List any source files likely involved.

Respond ONLY in this exact JSON format (no markdown, no extra text):
{
  "root_cause": "...",
  "relevant_files": ["file1.py", "file2.py"]
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


def root_cause_agent(state: IncidentState) -> dict:
    past_incidents = retrieve_context(state["correlated_error"], top_k=3)

    context_sections = ""
    for i, doc in enumerate(past_incidents, 1):
        context_sections += f"\n--- Past Incident {i} ---\n{doc}\n"

    human_content = (
        f"Correlated Error Summary:\n{state['correlated_error']}\n\n"
        f"Raw Error Logs:\n```\n{state['raw_logs']}\n```\n\n"
        f"Relevant Past Incidents:{context_sections if context_sections else ' None found.'}"
    )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    parsed = _parse_json(response.content)

    return {
        "root_cause": parsed.get("root_cause", ""),
        "relevant_files": parsed.get("relevant_files", []),
        "status": "root_cause_identified",
    }
