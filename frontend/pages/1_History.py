import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.history import list_incidents, get_incident, delete_incident, delete_all_incidents

st.set_page_config(
    page_title="Incident History",
    page_icon="📋",
    layout="wide",
)

SEVERITY_CONFIG = {
    "P0": ("🔴 P0", "error"),
    "P1": ("🟠 P1", "warning"),
    "P2": ("🟡 P2", "info"),
}

def _severity_badge(severity: str, reason: str = "") -> None:
    label, kind = SEVERITY_CONFIG.get(severity, ("⚪ ?", "info"))
    msg = f"**{label}**" + (f" — {reason}" if reason else "")
    getattr(st, kind)(msg)


st.title("📋 Incident History")
st.caption("All past pipeline runs, newest first.")

incidents = list_incidents(limit=100)

if not incidents:
    st.info("No incidents recorded yet. Run the pipeline from the main page to see history here.")
    st.stop()

# ---------------------------------------------------------------------------
# Controls row: severity filter + clear all
# ---------------------------------------------------------------------------

col_filter, col_clear = st.columns([5, 1])

with col_filter:
    sev_filter = st.multiselect(
        "Filter by severity",
        options=["P0", "P1", "P2"],
        default=["P0", "P1", "P2"],
        format_func=lambda x: {"P0": "🔴 P0 — Critical", "P1": "🟠 P1 — High", "P2": "🟡 P2 — Medium"}[x],
        label_visibility="collapsed",
    )

with col_clear:
    if st.button("Clear All", type="secondary", use_container_width=True):
        st.session_state["_confirm_clear"] = True

if st.session_state.get("_confirm_clear"):
    st.warning("This will permanently delete all incident records.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, delete all", type="primary"):
        delete_all_incidents()
        st.session_state.pop("_confirm_clear", None)
        st.rerun()
    if c2.button("Cancel"):
        st.session_state.pop("_confirm_clear", None)
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Incident rows
# ---------------------------------------------------------------------------

filtered = [i for i in incidents if i.get("severity", "P2") in sev_filter]

if not filtered:
    st.info("No incidents match the selected severity filters.")
    st.stop()

for inc in filtered:
    customers = inc["affected_customers"]
    customer_str = ", ".join(customers) if customers else "—"
    status = (inc.get("status") or "").replace("_", " ").title()
    tests_badge = "PASSED" if inc["tests_passed"] else ("ESCALATED" if inc["escalate_to_human"] else "FAILED")
    severity = inc.get("severity") or "P2"
    sev_icon = {"P0": "🔴", "P1": "🟠", "P2": "🟡"}.get(severity, "⚪")
    error_preview = (inc.get("correlated_error") or "No summary")[:70]
    if len(inc.get("correlated_error") or "") > 70:
        error_preview += "…"

    with st.expander(
        f"{sev_icon} **{severity}** · **#{inc['id']}** · {inc['timestamp']}  |  {status}  |  {error_preview}",
        expanded=False,
    ):
        # Severity badge
        _severity_badge(severity, inc.get("severity_reason", ""))

        # Metrics row
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Status", status)
        m2.metric("Customers", len(customers))
        m3.metric("Retries", inc["retry_count"])
        m4.metric("Tests", tests_badge)
        m5.metric("Time (s)", f"{inc['run_time_seconds']:.1f}")

        # Full detail — fetch on demand
        full = get_incident(inc["id"])
        if full:
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "Root Cause", "Fix Applied", "Test Results", "Customer Replies", "Postmortem"
            ])

            with tab1:
                st.markdown(f"**Root Cause:**\n\n{full.get('root_cause') or '—'}")
                files = full.get("relevant_files", [])
                if files:
                    st.markdown(f"**Relevant Files:** `{'`, `'.join(files)}`")
                if full.get("correlated_error"):
                    st.info(f"**Correlated Error:** {full['correlated_error']}")
                if customers:
                    st.markdown(f"**Affected Customers:** {customer_str}")

            with tab2:
                st.code(full.get("code_patch") or "No patch generated.", language="text")
                if full.get("patch_explanation"):
                    st.markdown(f"**Explanation:** {full['patch_explanation']}")

            with tab3:
                st.code(full.get("test_results") or "No test output.", language="text")
                if full.get("escalate_to_human"):
                    st.error("Max retries exceeded — escalated to human engineer.")

            with tab4:
                replies = full.get("customer_replies", [])
                if replies:
                    for reply in replies:
                        st.info(reply)
                        st.divider()
                else:
                    st.write("No customer replies generated.")

            with tab5:
                report = full.get("postmortem_report", "")
                if report:
                    st.markdown(report)
                    st.download_button(
                        label="Download Postmortem (Markdown)",
                        data=report,
                        file_name=f"postmortem_incident_{inc['id']}.md",
                        mime="text/markdown",
                        key=f"dl_{inc['id']}",
                    )
                else:
                    st.write("No report generated.")

        st.divider()
        if st.button("Delete this record", key=f"del_{inc['id']}"):
            delete_incident(inc["id"])
            st.rerun()
