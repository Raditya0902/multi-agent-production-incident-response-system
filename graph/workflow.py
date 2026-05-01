import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from agents.state import IncidentState
from agents.correlation_agent import correlation_agent
from agents.severity_agent import severity_agent
from agents.root_cause_agent import root_cause_agent
from agents.fix_generator_agent import fix_generator_agent
from agents.execution_agent import execution_agent
from agents.critic_agent import critic_agent
from agents.customer_response_agent import customer_response_agent
from agents.incident_report_agent import incident_report_agent

load_dotenv()


def route_after_execution(state: IncidentState) -> str:
    if state["tests_passed"]:
        return "customer_response"
    max_retries = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
    if state["retry_count"] >= max_retries:
        return "escalate"
    return "critic"


def escalation_node(state: IncidentState) -> dict:
    report = f"""# ESCALATION REQUIRED — Human Review Needed

The incident could not be automatically resolved after {state['retry_count']} fix attempt(s).

## Last Known Root Cause
{state.get('root_cause', 'Unknown')}

## Last Patch Attempted
```
{state.get('code_patch', 'None')}
```

## Last Test Output
```
{state.get('test_results', 'None')}
```

## Last Critic Feedback
{state.get('critic_feedback', 'None')}

## Immediate Action Required
A human engineer must review and apply a fix manually.
Affected customers: {', '.join(state.get('affected_customers', []))}
"""
    return {
        "escalate_to_human": True,
        "postmortem_report": report,
        "status": "escalated",
    }


def build_phase1():
    """Diagnosis phase: correlation → severity → root_cause → fix_generator.
    Stops here so a human can review the severity-tagged patch before execution."""
    workflow = StateGraph(IncidentState)
    workflow.add_node("correlation", correlation_agent)
    workflow.add_node("severity", severity_agent)
    workflow.add_node("root_cause", root_cause_agent)
    workflow.add_node("fix_generator", fix_generator_agent)
    workflow.set_entry_point("correlation")
    workflow.add_edge("correlation", "severity")
    workflow.add_edge("severity", "root_cause")
    workflow.add_edge("root_cause", "fix_generator")
    workflow.add_edge("fix_generator", END)
    return workflow.compile()


def build_phase2():
    """Execution phase: runs after human approves the patch.
    Retries after test failures skip the human gate — only the first patch needs approval."""
    workflow = StateGraph(IncidentState)
    workflow.add_node("execution", execution_agent)
    workflow.add_node("critic", critic_agent)
    workflow.add_node("fix_generator", fix_generator_agent)
    workflow.add_node("customer_response", customer_response_agent)
    workflow.add_node("incident_report", incident_report_agent)
    workflow.add_node("escalate", escalation_node)
    workflow.set_entry_point("execution")
    workflow.add_conditional_edges(
        "execution",
        route_after_execution,
        {
            "customer_response": "customer_response",
            "critic": "critic",
            "escalate": "escalate",
        },
    )
    workflow.add_edge("critic", "fix_generator")
    workflow.add_edge("fix_generator", "execution")
    workflow.add_edge("customer_response", "incident_report")
    workflow.add_edge("incident_report", END)
    workflow.add_edge("escalate", END)
    return workflow.compile()


def build_workflow():
    """Full pipeline with no human gate — used by tests and backward-compat callers."""
    workflow = StateGraph(IncidentState)
    workflow.add_node("correlation", correlation_agent)
    workflow.add_node("severity", severity_agent)
    workflow.add_node("root_cause", root_cause_agent)
    workflow.add_node("fix_generator", fix_generator_agent)
    workflow.add_node("execution", execution_agent)
    workflow.add_node("critic", critic_agent)
    workflow.add_node("customer_response", customer_response_agent)
    workflow.add_node("incident_report", incident_report_agent)
    workflow.add_node("escalate", escalation_node)
    workflow.set_entry_point("correlation")
    workflow.add_edge("correlation", "severity")
    workflow.add_edge("severity", "root_cause")
    workflow.add_edge("root_cause", "fix_generator")
    workflow.add_edge("fix_generator", "execution")
    workflow.add_conditional_edges(
        "execution",
        route_after_execution,
        {
            "customer_response": "customer_response",
            "critic": "critic",
            "escalate": "escalate",
        },
    )
    workflow.add_edge("critic", "fix_generator")
    workflow.add_edge("customer_response", "incident_report")
    workflow.add_edge("incident_report", END)
    workflow.add_edge("escalate", END)
    return workflow.compile()


phase1_app = build_phase1()
phase2_app = build_phase2()
app = build_workflow()
