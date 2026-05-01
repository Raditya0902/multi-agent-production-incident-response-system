from datetime import datetime, timezone
from langchain_core.messages import HumanMessage

from agents import llm
from agents.state import IncidentState


def incident_report_agent(state: IncidentState) -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # One LLM call only for the prevention section — factual sections are template-based
    prevention_prompt = (
        f"Given this root cause: {state['root_cause']}\n"
        f"List 3-4 concrete, specific prevention measures to stop this from recurring. "
        f"Each on its own line starting with '- '. Under 150 words total."
    )
    prevention = llm.invoke([HumanMessage(content=prevention_prompt)]).content.strip()

    affected = state.get("affected_customers", [])
    affected_list = "\n".join(f"- {c}" for c in affected) or "- None identified"

    replies = state.get("customer_replies", [])
    replies_section = "\n\n".join(replies) if replies else "No customer replies generated."

    test_status = "PASSED" if state.get("tests_passed") else (
        "ESCALATED TO HUMAN" if state.get("escalate_to_human") else "FAILED"
    )

    report = f"""# Incident Report — {timestamp}

## Summary
{state.get("correlated_error", "No summary available.")}

## Root Cause
{state.get("root_cause", "Not identified.")}

## Relevant Files
{", ".join(state.get("relevant_files", [])) or "Unknown"}

## Fix Applied

```
{state.get("code_patch", "No patch generated.")}
```

**Explanation:** {state.get("patch_explanation", "")}

## Test Results
**Status:** {test_status}
**Retry Attempts:** {state.get("retry_count", 0)}

```
{state.get("test_results", "No test output.")}
```

## Customers Affected
{affected_list}

## Customer Communications

{replies_section}

## Prevention Recommendations
{prevention}
"""

    return {
        "postmortem_report": report,
        "status": "complete",
    }
