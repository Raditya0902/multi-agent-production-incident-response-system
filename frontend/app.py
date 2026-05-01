import json
import os
import sys
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.workflow import phase1_app, phase2_app
from agents.fix_generator_agent import fix_generator_agent
from agents.state import create_initial_state
from db.history import save_incident, init_db
from notifications.slack import notify as slack_notify, is_configured as slack_configured
from notifications.github_pr import create_pr, is_configured as github_configured

init_db()


SEVERITY_CONFIG = {
    "P0": ("🔴 P0 — Critical", "error"),
    "P1": ("🟠 P1 — High",     "warning"),
    "P2": ("🟡 P2 — Medium",   "info"),
}

def _severity_badge(severity: str, reason: str = "") -> None:
    label, kind = SEVERITY_CONFIG.get(severity, ("⚪ Unknown", "info"))
    msg = f"**{label}**" + (f" — {reason}" if reason else "")
    getattr(st, kind)(msg)


def _show_rate_limit_error(e=None):
    st.error(
        "**Groq daily token limit reached.**\n\n"
        "In your `.env` file, change:\n"
        "```\nLLM_MODEL=llama-3.1-8b-instant\n```\n"
        "then reload the page. Or wait until tomorrow for the quota to reset."
    )


def _show_pipeline_error(e):
    err = str(e)
    if "tokens per day" in err or "rate_limit_exceeded" in err:
        _show_rate_limit_error(e)
    else:
        st.error(f"Pipeline error: {e}")


st.set_page_config(
    page_title="Production Incident Response",
    page_icon="🚨",
    layout="wide",
)

st.title("🚨 Production Incident Response System")
st.caption("Multi-agent AI pipeline: correlate → diagnose → fix → **human approval** → validate → notify → report")

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
# hitl_phase controls the page:
#   "input"              — initial state, show input form
#   "awaiting_approval"  — phase1 done, show patch + approve/reject UI
#   "complete"           — phase2 done, show results

def reset_run():
    for key in ("hitl_phase", "hitl_state", "hitl_agent_log", "hitl_run_start",
                "last_result", "run_time", "_loaded_logs", "_loaded_complaints"):
        st.session_state.pop(key, None)


phase = st.session_state.get("hitl_phase", "input")

# ---------------------------------------------------------------------------
# Sample data loader
# ---------------------------------------------------------------------------

def load_sample_data(scenario: str):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_map = {
        "incident_indexerror": "indexerror_log.txt",
        "incident_keyerror":   "keyerror_log.txt",
        "incident_timeout":    "timeout_log.txt",
    }
    logs_path = os.path.join(root, "data", "sample_logs", log_map.get(scenario, "indexerror_log.txt"))
    complaints_path = os.path.join(root, "data", "sample_complaints", "complaints.json")
    logs = open(logs_path).read() if os.path.exists(logs_path) else ""
    complaints_json = json.load(open(complaints_path)) if os.path.exists(complaints_path) else {}
    return logs, "\n".join(c["message"] for c in complaints_json.get(scenario, []))


# ---------------------------------------------------------------------------
# SECTION 1: Input form (shown only in "input" phase)
# ---------------------------------------------------------------------------

if phase == "input":
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Error Logs / Stack Trace")
        error_logs = st.text_area(
            "error_logs", label_visibility="collapsed",
            value=st.session_state.get("_loaded_logs", ""),
            height=220,
            placeholder="2024-11-15 14:32:01 ERROR ...\nTraceback (most recent call last):\n  ...",
        )
    with col_right:
        st.subheader("Customer Complaints (one per line)")
        complaints_text = st.text_area(
            "complaints", label_visibility="collapsed",
            value=st.session_state.get("_loaded_complaints", ""),
            height=220,
            placeholder="Your app keeps crashing when I upload my file!\nGetting an error every time I submit.",
        )

    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    with c1:
        scenario = st.selectbox("scenario", label_visibility="collapsed",
            options=["incident_indexerror", "incident_keyerror", "incident_timeout"],
            format_func=lambda x: {
                "incident_indexerror": "IndexError — file upload crash",
                "incident_keyerror":   "KeyError — payment failure",
                "incident_timeout":    "Timeout — DB pool exhausted",
            }[x])
    with c2:
        if st.button("Load Sample Data", use_container_width=True):
            logs, complaints = load_sample_data(scenario)
            st.session_state["_loaded_logs"] = logs
            st.session_state["_loaded_complaints"] = complaints
            st.rerun()
    with c4:
        run_clicked = st.button("Run", type="primary", use_container_width=True,
                                disabled=not (error_logs and complaints_text))

    st.divider()

    if run_clicked:
        complaints = [l.strip() for l in complaints_text.split("\n") if l.strip()]
        initial_state = create_initial_state(complaints=complaints, logs=error_logs)
        st.session_state["hitl_state"] = dict(initial_state)
        st.session_state["hitl_agent_log"] = {}
        st.session_state["hitl_run_start"] = datetime.now()
        st.session_state["hitl_phase"] = "running_phase1"
        st.rerun()

# ---------------------------------------------------------------------------
# SECTION 2: Phase 1 running (transient — runs immediately and transitions)
# ---------------------------------------------------------------------------

elif phase == "running_phase1":
    state = st.session_state["hitl_state"]
    agent_log = st.session_state["hitl_agent_log"]
    start = st.session_state["hitl_run_start"]

    st.subheader("Agent Activity")
    phase1_labels = {
        "correlation":   "Correlation Agent — linking complaints to errors",
        "severity":      "Severity Agent — classifying incident priority",
        "root_cause":    "Root Cause Agent — diagnosing root cause (RAG)",
        "fix_generator": "Fix Generator Agent — generating code patch",
    }
    slots = {k: st.empty() for k in phase1_labels}
    for k, label in phase1_labels.items():
        slots[k].markdown(f"⏳ {label}")

    try:
        with st.spinner("Diagnosing incident..."):
            for step in phase1_app.stream(state):
                node = list(step.keys())[0]
                state.update(step[node])
                elapsed = (datetime.now() - start).seconds
                agent_log[node] = elapsed
                if node in slots:
                    slots[node].success(f"✅ {phase1_labels[node]} ({elapsed}s)")

        st.session_state["hitl_state"] = state
        st.session_state["hitl_agent_log"] = agent_log
        st.session_state["hitl_phase"] = "awaiting_approval"
        st.rerun()

    except RuntimeError as e:
        _show_rate_limit_error(e)
    except Exception as e:
        _show_pipeline_error(e)

# ---------------------------------------------------------------------------
# SECTION 3: Awaiting human approval
# ---------------------------------------------------------------------------

elif phase == "awaiting_approval":
    state = st.session_state["hitl_state"]
    agent_log = st.session_state["hitl_agent_log"]
    max_retries = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))

    # Show completed phase1 agents statically
    st.subheader("Agent Activity")
    phase1_labels = {
        "correlation":   "Correlation Agent — linking complaints to errors",
        "severity":      "Severity Agent — classifying incident priority",
        "root_cause":    "Root Cause Agent — diagnosing root cause (RAG)",
        "fix_generator": "Fix Generator Agent — generating code patch",
    }
    for k, label in phase1_labels.items():
        elapsed = agent_log.get(k, "—")
        t = f" ({elapsed}s)" if isinstance(elapsed, int) else ""
        st.success(f"✅ {label}{t}")

    st.divider()

    # Approval panel
    rejection_count = state.get("retry_count", 0)
    attempts_left = max_retries - rejection_count

    # Severity badge
    severity = state.get("severity", "P2")
    severity_reason = state.get("severity_reason", "")
    _severity_badge(severity, severity_reason)

    st.subheader("🔍 Human Approval Required")
    if rejection_count > 0:
        st.warning(f"This is revised patch #{rejection_count + 1}. Attempts remaining: {attempts_left}")

    with st.expander("Root Cause Context", expanded=False):
        st.markdown(state.get("root_cause", "—"))
        files = state.get("relevant_files", [])
        if files:
            st.markdown(f"**Relevant files:** `{'`, `'.join(files)}`")

    st.markdown("**Proposed Patch**")
    st.code(state.get("code_patch", "No patch generated."), language="text")

    explanation = state.get("patch_explanation", "")
    if explanation:
        st.info(f"**Explanation:** {explanation}")

    feedback = st.text_area(
        "Rejection reason (required if rejecting, optional if approving)",
        placeholder="e.g. The fix doesn't handle the case where items is None, only empty...",
        height=80,
        key=f"feedback_{rejection_count}",
    )

    col_approve, col_reject, col_cancel = st.columns([2, 2, 1])

    with col_approve:
        if st.button("Approve & Run Tests", type="primary", use_container_width=True):
            st.session_state["hitl_phase"] = "running_phase2"
            st.rerun()

    with col_reject:
        reject_disabled = attempts_left <= 1  # last chance must approve or cancel
        if st.button("Reject — Regenerate Patch", use_container_width=True,
                     disabled=reject_disabled,
                     help="Disabled on last attempt — approve or cancel."):
            if not feedback.strip():
                st.error("Please provide a rejection reason so the AI can improve the patch.")
                st.stop()
            # Inject human feedback and regenerate fix — no LangGraph needed, call directly
            state["critic_feedback"] = f"[Human reviewer rejected this patch]: {feedback.strip()}"
            state["retry_count"] = rejection_count + 1
            updated = fix_generator_agent(state)
            state.update(updated)
            st.session_state["hitl_state"] = state
            # Stay in awaiting_approval with new patch
            st.rerun()

    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            reset_run()
            st.rerun()

# ---------------------------------------------------------------------------
# SECTION 4: Phase 2 running (transient)
# ---------------------------------------------------------------------------

elif phase == "running_phase2":
    state = st.session_state["hitl_state"]
    agent_log = st.session_state["hitl_agent_log"]
    start = st.session_state["hitl_run_start"]

    # Show phase1 agents statically
    st.subheader("Agent Activity")
    phase1_labels = {
        "correlation":   "Correlation Agent — linking complaints to errors",
        "severity":      "Severity Agent — classifying incident priority",
        "root_cause":    "Root Cause Agent — diagnosing root cause (RAG)",
        "fix_generator": "Fix Generator Agent — generating code patch",
    }
    for k, label in phase1_labels.items():
        elapsed = agent_log.get(k, "—")
        t = f" ({elapsed}s)" if isinstance(elapsed, int) else ""
        st.success(f"✅ {label}{t}")

    st.markdown("**✅ Patch approved by human reviewer**")
    st.divider()

    phase2_labels = {
        "execution":        "Execution Agent — running tests in sandbox",
        "critic":           "Critic Agent — analyzing failure",
        "fix_generator":    "Fix Generator Agent — regenerating patch",
        "customer_response":"Customer Response Agent — drafting replies",
        "incident_report":  "Incident Report Agent — generating postmortem",
        "escalate":         "Escalation — human review required",
    }
    slots = {k: st.empty() for k in phase2_labels}
    for k, label in phase2_labels.items():
        slots[k].markdown(f"⏳ {label}")

    phase2_start = datetime.now()

    try:
        with st.spinner("Executing and validating fix..."):
            for step in phase2_app.stream(state):
                node = list(step.keys())[0]
                state.update(step[node])
                elapsed = (datetime.now() - phase2_start).seconds
                agent_log[node] = elapsed
                if node in slots:
                    label = phase2_labels[node]
                    if node == "escalate":
                        slots[node].error(f"🆘 {label} ({elapsed}s)")
                    else:
                        slots[node].success(f"✅ {label} ({elapsed}s)")

        total_time = (datetime.now() - start).total_seconds()
        incident_id = save_incident(state, total_time)
        slack_sent = slack_notify(state, total_time, incident_id)
        pr_url = create_pr(state, incident_id)
        st.session_state["hitl_state"] = state
        st.session_state["hitl_agent_log"] = agent_log
        st.session_state["last_result"] = state
        st.session_state["run_time"] = total_time
        st.session_state["slack_notified"] = slack_sent
        st.session_state["github_pr_url"] = pr_url
        st.session_state["hitl_phase"] = "complete"
        st.rerun()

    except RuntimeError as e:
        _show_rate_limit_error(e)
    except Exception as e:
        _show_pipeline_error(e)

# ---------------------------------------------------------------------------
# SECTION 5: Complete — show results
# ---------------------------------------------------------------------------

elif phase == "complete":
    state = st.session_state["hitl_state"]
    agent_log = st.session_state["hitl_agent_log"]
    run_time = st.session_state.get("run_time", 0)

    # Full agent activity log (static)
    st.subheader("Agent Activity")
    all_labels = {
        "correlation":       "Correlation Agent — linking complaints to errors",
        "severity":          "Severity Agent — classifying incident priority",
        "root_cause":        "Root Cause Agent — diagnosing root cause (RAG)",
        "fix_generator":     "Fix Generator Agent — generating code patch",
        "execution":         "Execution Agent — running tests in sandbox",
        "critic":            "Critic Agent — analyzing failure",
        "customer_response": "Customer Response Agent — drafting replies",
        "incident_report":   "Incident Report Agent — generating postmortem",
        "escalate":          "Escalation — human review required",
    }
    for k, label in all_labels.items():
        if k not in agent_log:
            continue
        elapsed = agent_log[k]
        t = f" ({elapsed}s)" if isinstance(elapsed, int) else ""
        if k == "escalate":
            st.error(f"🆘 {label}{t}")
        else:
            st.success(f"✅ {label}{t}")

    st.markdown("**✅ Patch was approved by human reviewer**")

    col_newrun, col_slack, col_pr = st.columns([1, 3, 3])
    with col_newrun:
        if st.button("New Run", type="secondary"):
            reset_run()
            st.rerun()
    with col_slack:
        if st.session_state.get("slack_notified"):
            channel = os.getenv("SLACK_INCIDENT_CHANNEL", "#incidents")
            if state.get("escalate_to_human"):
                channel = os.getenv("SLACK_ESCALATION_CHANNEL") or channel
            st.success(f"📣 Slack notification sent to **{channel}**")
        elif slack_configured():
            st.warning("Slack is configured but notification failed — check logs.")
    with col_pr:
        pr_url = st.session_state.get("github_pr_url")
        if pr_url:
            st.success(f"🔗 [Pull Request opened on GitHub]({pr_url})")
        elif github_configured() and state.get("tests_passed"):
            st.warning("GitHub PR creation failed — check logs.")
        elif github_configured() and not state.get("tests_passed"):
            st.info("GitHub PR skipped — tests did not pass.")

    st.divider()

    # Results
    st.subheader("Results")
    _severity_badge(state.get("severity", "P2"), state.get("severity_reason", ""))
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Status", (state.get("status") or "—").replace("_", " ").title())
    m2.metric("Customers Affected", len(state.get("affected_customers", [])))
    m3.metric("Retry Attempts", state.get("retry_count", 0))
    m4.metric("Tests", "PASSED" if state.get("tests_passed") else "FAILED")
    m5.metric("Time (s)", f"{run_time:.1f}")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Root Cause", "Fix Applied", "Test Results", "Customer Replies", "Postmortem"
    ])

    with tab1:
        st.markdown(f"**Root Cause:**\n\n{state.get('root_cause', 'Not identified.')}")
        files = state.get("relevant_files", [])
        if files:
            st.markdown(f"**Relevant Files:** `{'`, `'.join(files)}`")
        if state.get("correlated_error"):
            st.info(f"**Correlated Error:** {state['correlated_error']}")
        affected = state.get("affected_customers", [])
        if affected:
            st.markdown("**Affected Customers:** " + ", ".join(affected))

    with tab2:
        st.code(state.get("code_patch", "No patch generated."), language="text")
        if state.get("patch_explanation"):
            st.markdown(f"**Explanation:** {state['patch_explanation']}")

    with tab3:
        st.code(state.get("test_results", "No test output."), language="text")
        if state.get("escalate_to_human"):
            st.error("Max retries exceeded — escalated to human engineer.")

    with tab4:
        replies = state.get("customer_replies", [])
        if replies:
            for reply in replies:
                st.info(reply)
                st.divider()
        else:
            st.write("No customer replies generated.")

    with tab5:
        report = state.get("postmortem_report", "")
        if report:
            st.markdown(report)
            st.download_button(
                label="Download Postmortem (Markdown)",
                data=report,
                file_name=f"postmortem_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
            )
        else:
            st.write("No report generated.")


