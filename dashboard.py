from __future__ import annotations

import pandas as pd
import streamlit as st

from risk_engine import (
    draft_notification,
    enrich_with_resource_context,
    load_data,
    score_dataframe,
    score_order,
)


st.set_page_config(page_title="Diagnostic TAT Early Warning", layout="wide")
st.title("Diagnostic TAT Early Warning")
st.caption("Local prototype using synthetic challenge data. No messages are sent.")


@st.cache_data
def dashboard_data():
    orders, patients, resources = load_data()
    recent = orders.sort_values("order_time", ascending=False).head(5000)
    recent = enrich_with_resource_context(recent, resources)
    scored = score_dataframe(recent)
    return recent.merge(scored, on=["order_id", "patient_id"]), patients


queue, patients = dashboard_data()
threshold = st.sidebar.slider("Alert threshold", 0.0, 1.0, 0.40, 0.05)
category = st.sidebar.selectbox("Test category", ["all"] + sorted(queue["test_category"].unique()))
filtered = queue[queue["breach_probability"] >= threshold].copy()
if category != "all":
    filtered = filtered[filtered["test_category"] == category]

total = len(queue)
alerts = len(filtered)
critical = int(filtered["risk_level"].eq("critical").sum())
off_track = int((~queue["on_track_at_checkpoint"].astype(bool)).sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Orders monitored", f"{total:,}")
c2.metric("Alerts", f"{alerts:,}")
c3.metric("Critical", f"{critical:,}")
c4.metric("Off-track checkpoints", f"{off_track:,}")

st.subheader("At-risk queue")
display_columns = [
    "order_id",
    "test_code",
    "test_category",
    "priority",
    "breach_probability",
    "risk_level",
    "projected_slip_hours",
    "capacity_load_ratio",
    "downtime_minutes",
]
st.dataframe(
    filtered.sort_values("breach_probability", ascending=False)[display_columns],
    use_container_width=True,
    hide_index=True,
)

if not filtered.empty:
    st.subheader("Review an alert")
    order_id = st.selectbox("Order", filtered["order_id"].tolist())
    order = filtered[filtered["order_id"] == order_id].iloc[0].to_dict()
    risk = score_order(order)
    opted_in = bool(
        patients.set_index("patient_id").loc[order["patient_id"], "notification_opt_in"]
    )
    notification = draft_notification(order, risk, opted_in)

    left, right = st.columns(2)
    with left:
        st.write(risk.to_dict())
    with right:
        st.write(notification)
        st.info("Staff approval is required. This prototype never sends messages.")
