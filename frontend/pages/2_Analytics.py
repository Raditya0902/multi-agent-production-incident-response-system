import os
import sys
from collections import Counter, defaultdict

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.history import get_analytics_data

st.set_page_config(
    page_title="Incident Analytics",
    page_icon="📊",
    layout="wide",
)

_SEV_COLORS = {"P0": "#e53935", "P1": "#fb8c00", "P2": "#fdd835"}
_OUTCOME_COLORS = {
    "Tests Passed": "#43a047",
    "Escalated": "#e53935",
    "Tests Failed": "#fb8c00",
}

st.title("📊 Incident Analytics")
st.caption("Aggregate metrics across all pipeline runs.")

data = get_analytics_data()

if not data:
    st.info("No incident data yet. Run the pipeline from the main page to see analytics here.")
    st.stop()

# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

total = len(data)
sev_counts = Counter(d["severity"] for d in data)
pass_count = sum(1 for d in data if d["tests_passed"])
escalated_count = sum(1 for d in data if d["escalate_to_human"])
failed_count = total - pass_count - escalated_count
pass_rate = pass_count / total * 100
avg_mttr = sum(d["run_time_seconds"] for d in data) / total
total_customers = sum(len(d["affected_customers"]) for d in data)
avg_retries = sum(d["retry_count"] for d in data) / total

# ---------------------------------------------------------------------------
# Top metrics
# ---------------------------------------------------------------------------

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total Incidents", total)
m2.metric("P0 Critical", sev_counts.get("P0", 0))
m3.metric("P1 High", sev_counts.get("P1", 0))
m4.metric("Avg MTTR", f"{avg_mttr:.0f}s")
m5.metric("Tests Pass Rate", f"{pass_rate:.0f}%")
m6.metric("Customers Affected", total_customers)

st.divider()

# ---------------------------------------------------------------------------
# Row 1: Severity breakdown | Outcome breakdown
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    st.subheader("Severity Breakdown")
    severities = ["P0", "P1", "P2"]
    counts = [sev_counts.get(s, 0) for s in severities]
    fig_sev = px.pie(
        values=counts,
        names=severities,
        color=severities,
        color_discrete_map=_SEV_COLORS,
        hole=0.45,
    )
    fig_sev.update_traces(textinfo="label+percent+value")
    fig_sev.update_layout(showlegend=True, margin=dict(t=20, b=20))
    st.plotly_chart(fig_sev, use_container_width=True)

with col2:
    st.subheader("Outcome Breakdown")
    outcomes = ["Tests Passed", "Tests Failed", "Escalated"]
    outcome_vals = [pass_count, failed_count, escalated_count]
    fig_out = px.pie(
        values=outcome_vals,
        names=outcomes,
        color=outcomes,
        color_discrete_map=_OUTCOME_COLORS,
        hole=0.45,
    )
    fig_out.update_traces(textinfo="label+percent+value")
    fig_out.update_layout(showlegend=True, margin=dict(t=20, b=20))
    st.plotly_chart(fig_out, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 2: Incidents over time
# ---------------------------------------------------------------------------

st.subheader("Incidents Over Time")
date_counts: Counter = Counter()
sev_by_date: dict = defaultdict(lambda: Counter())
for d in data:
    date_str = d["timestamp"][:10]
    date_counts[date_str] += 1
    sev_by_date[date_str][d["severity"]] += 1

sorted_dates = sorted(date_counts.keys())

if len(sorted_dates) >= 2:
    rows_stacked = []
    for date in sorted_dates:
        for sev in ["P0", "P1", "P2"]:
            rows_stacked.append({
                "Date": date,
                "Severity": sev,
                "Count": sev_by_date[date].get(sev, 0),
            })
    fig_time = px.bar(
        rows_stacked,
        x="Date",
        y="Count",
        color="Severity",
        color_discrete_map=_SEV_COLORS,
        barmode="stack",
        labels={"Count": "Incidents"},
    )
    fig_time.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig_time, use_container_width=True)
else:
    st.info("Run more incidents on different days to see the trend chart.")

# ---------------------------------------------------------------------------
# Row 3: MTTR by severity | Retry distribution
# ---------------------------------------------------------------------------

col3, col4 = st.columns(2)

with col3:
    st.subheader("Avg MTTR by Severity")
    sev_times: dict = defaultdict(list)
    for d in data:
        sev_times[d["severity"]].append(d["run_time_seconds"])
    sev_labels = [s for s in ["P0", "P1", "P2"] if sev_times[s]]
    sev_avg = [sum(sev_times[s]) / len(sev_times[s]) for s in sev_labels]
    fig_mttr = px.bar(
        x=sev_labels,
        y=sev_avg,
        color=sev_labels,
        color_discrete_map=_SEV_COLORS,
        labels={"x": "Severity", "y": "Avg Time (s)"},
        text=[f"{v:.0f}s" for v in sev_avg],
    )
    fig_mttr.update_traces(textposition="outside")
    fig_mttr.update_layout(showlegend=False, margin=dict(t=30, b=10))
    st.plotly_chart(fig_mttr, use_container_width=True)

with col4:
    st.subheader("Retry Count Distribution")
    retry_counter: Counter = Counter(d["retry_count"] for d in data)
    max_retry = max(retry_counter.keys()) if retry_counter else 0
    retry_labels = [str(i) for i in range(max_retry + 1)]
    retry_vals = [retry_counter.get(i, 0) for i in range(max_retry + 1)]
    fig_retry = px.bar(
        x=retry_labels,
        y=retry_vals,
        labels={"x": "Retries", "y": "Incidents"},
        color_discrete_sequence=["#7b1fa2"],
        text=retry_vals,
    )
    fig_retry.update_traces(textposition="outside")
    fig_retry.update_layout(margin=dict(t=30, b=10))
    st.plotly_chart(fig_retry, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 4: Summary table
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Severity × Outcome Matrix")

matrix_rows = []
for sev in ["P0", "P1", "P2"]:
    sev_data = [d for d in data if d["severity"] == sev]
    if not sev_data:
        continue
    matrix_rows.append({
        "Severity": sev,
        "Total": len(sev_data),
        "Passed": sum(1 for d in sev_data if d["tests_passed"]),
        "Escalated": sum(1 for d in sev_data if d["escalate_to_human"]),
        "Avg MTTR (s)": f"{sum(d['run_time_seconds'] for d in sev_data) / len(sev_data):.1f}",
        "Avg Retries": f"{sum(d['retry_count'] for d in sev_data) / len(sev_data):.1f}",
        "Customers Hit": sum(len(d['affected_customers']) for d in sev_data),
    })

if matrix_rows:
    st.dataframe(matrix_rows, use_container_width=True, hide_index=True)
