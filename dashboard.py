from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from alert_runner import MailConfig, build_email, save_email_to_outbox, send_email
from risk_engine import (
    draft_notification,
    enrich_with_resource_context,
    load_data,
    score_dataframe,
    score_order,
)


st.set_page_config(
    page_title="Diagnostic TAT Command Center",
    page_icon="⏱️",
    layout="wide",
)
st.markdown(
    """
    <style>
    .stApp {background: #f4f7fb;}
    .block-container {padding-top: 1.5rem; max-width: 1500px;}
    [data-testid="stMetric"] {
        background: white; border: 1px solid #e5eaf2; border-radius: 14px;
        padding: 14px 18px; box-shadow: 0 4px 14px rgba(15, 23, 42, .05);
    }
    .hero {
        padding: 22px 26px; border-radius: 18px; color: white;
        background: linear-gradient(120deg, #0f3d63, #087e8b);
        margin-bottom: 18px;
    }
    .hero h1 {margin: 0 0 6px 0; font-size: 2rem;}
    .hero p {margin: 0; opacity: .9;}
    .risk-card {
        background: white; border-radius: 14px; padding: 18px;
        border-left: 6px solid #ef4444; box-shadow: 0 4px 14px rgba(15, 23, 42, .05);
    }
    .muted {color: #64748b;}
    </style>
    <div class="hero">
      <h1>Diagnostic TAT Command Center</h1>
      <p>Predict SLA breaches at the interim checkpoint, prioritize intervention, and trigger alerts.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def dashboard_data():
    orders, patients, resources = load_data()
    recent = orders.sort_values("order_time", ascending=False).head(5000)
    recent = enrich_with_resource_context(recent, resources)
    scored = score_dataframe(recent)
    return recent.merge(scored, on=["order_id", "patient_id"]), patients, resources


def risk_badge(level: str) -> str:
    colors = {
        "critical": "#dc2626",
        "high": "#ea580c",
        "medium": "#ca8a04",
        "low": "#16a34a",
    }
    return (
        f"<span style='background:{colors[level]};color:white;padding:5px 10px;"
        f"border-radius:999px;font-weight:700'>{level.upper()}</span>"
    )


def make_alert_item(order: dict, opted_in: bool) -> dict:
    risk = score_order(order)
    return {
        "order": order,
        "risk": risk,
        "notification": draft_notification(order, risk, opted_in),
    }


queue, patients, resources = dashboard_data()
patients_by_id = patients.set_index("patient_id")
tab_command, tab_review, tab_trigger, tab_delivery = st.tabs(
    ["Command Center", "Alert Review", "Trigger Lab", "Delivery Setup"]
)

with tab_command:
    threshold = st.sidebar.slider("Alert threshold", 0.0, 1.0, 0.40, 0.05)
    category = st.sidebar.selectbox(
        "Test category", ["all"] + sorted(queue["test_category"].unique())
    )
    priority = st.sidebar.multiselect(
        "Priority", sorted(queue["priority"].unique()), default=sorted(queue["priority"].unique())
    )
    filtered = queue[
        (queue["breach_probability"] >= threshold) & queue["priority"].isin(priority)
    ].copy()
    if category != "all":
        filtered = filtered[filtered["test_category"] == category]

    total = len(queue)
    alerts = len(filtered)
    critical = int(filtered["risk_level"].eq("critical").sum())
    off_track = int((~queue["on_track_at_checkpoint"].astype(bool)).sum())
    opted_in_alerts = int(
        filtered["patient_id"].isin(
            patients[patients["notification_opt_in"].astype(bool)]["patient_id"]
        ).sum()
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Orders monitored", f"{total:,}")
    c2.metric("Active alerts", f"{alerts:,}")
    c3.metric("Critical", f"{critical:,}")
    c4.metric("Off track", f"{off_track:,}")
    c5.metric("Consent eligible", f"{opted_in_alerts:,}")

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Prioritized intervention queue")
        display = filtered.sort_values("breach_probability", ascending=False).copy()
        display["breach_probability"] = display["breach_probability"].map(lambda x: f"{x:.1%}")
        display["capacity_load_ratio"] = display["capacity_load_ratio"].map(lambda x: f"{x:.0%}")
        st.dataframe(
            display[
                [
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
            ],
            width="stretch",
            hide_index=True,
            height=460,
        )
    with right:
        st.subheader("Risk mix")
        mix = filtered["risk_level"].value_counts().reindex(
            ["critical", "high", "medium"], fill_value=0
        )
        st.bar_chart(mix, horizontal=True)
        st.subheader("Resource pressure")
        resource_pressure = (
            filtered.groupby("test_category")["capacity_load_ratio"]
            .mean()
            .sort_values(ascending=False)
            .head(7)
        )
        st.bar_chart(resource_pressure)

with tab_review:
    review_queue = queue[queue["breach_probability"] >= 0.40].sort_values(
        "breach_probability", ascending=False
    )
    selected_id = st.selectbox("Select an at-risk order", review_queue["order_id"].tolist())
    selected_order = review_queue[review_queue["order_id"] == selected_id].iloc[0].to_dict()
    selected_opt_in = bool(
        patients_by_id.loc[selected_order["patient_id"], "notification_opt_in"]
    )
    selected_alert = make_alert_item(selected_order, selected_opt_in)
    selected_risk = selected_alert["risk"]
    selected_notification = selected_alert["notification"]

    st.markdown(
        f"<div class='risk-card'><h3>{selected_risk.order_id} &nbsp; "
        f"{risk_badge(selected_risk.risk_level)}</h3>"
        f"<p><b>{selected_order['test_code']}</b> · {selected_order['test_category']} · "
        f"{selected_order['priority']}</p>"
        f"<h2>{selected_risk.breach_probability:.1%} breach risk</h2>"
        f"<p>Projected slip: <b>{selected_risk.projected_slip_hours:+.2f} hours</b></p></div>",
        unsafe_allow_html=True,
    )
    a, b, c = st.columns(3)
    a.metric("Promised completion", selected_risk.promised_completion_time.replace("T", " "))
    b.metric("Estimated completion", selected_risk.estimated_completion_time.replace("T", " "))
    c.metric("Hours until SLA", selected_risk.hours_until_sla)
    reason_col, notify_col = st.columns(2)
    with reason_col:
        st.subheader("Why this alert fired")
        for reason in selected_risk.reasons:
            st.write(f"- {reason}")
        st.info(selected_risk.recommended_action)
    with notify_col:
        st.subheader("Patient communication")
        st.write(f"Consent status: **{selected_notification['status']}**")
        if selected_notification["message"]:
            st.text_area(
                "Draft notification",
                selected_notification["message"],
                height=150,
                disabled=True,
            )
        else:
            st.warning("Patient communication is blocked because consent is unavailable.")

with tab_trigger:
    st.subheader("Simulate a checkpoint and trigger a local alert")
    st.caption(
        "Enter values known at the interim checkpoint. The trigger creates a local .eml file "
        "or sends through configured SMTP."
    )
    categories = sorted(queue["test_category"].unique())
    test_codes = sorted(queue["test_code"].unique())
    with st.form("trigger_form"):
        row1 = st.columns(4)
        order_id = row1[0].text_input("Order ID", value=f"LOCAL-{datetime.now():%Y%m%d-%H%M%S}")
        patient_id = row1[1].text_input("Patient ID", value="LOCAL-PATIENT")
        test_code = row1[2].selectbox("Test", test_codes)
        test_category = row1[3].selectbox("Test category", categories)

        row2 = st.columns(4)
        priority_value = row2[0].selectbox("Priority", ["routine", "urgent", "stat"])
        promised = row2[1].number_input("Promised SLA hours", 0.5, 168.0, 6.0, 0.5)
        elapsed = row2[2].number_input("Elapsed at checkpoint", 0.0, 168.0, 2.0, 0.5)
        remaining = row2[3].number_input("Expected remaining hours", 0.0, 336.0, 6.0, 0.5)

        row3 = st.columns(3)
        on_track = row3[0].toggle("Checkpoint marked on track", value=False)
        opted_in = row3[1].toggle("Patient notification consent", value=True)
        recipient = row3[2].text_input(
            "Operations alert recipient",
            value=os.environ.get("ALERT_RECIPIENTS", "diagnostics-operations@example.com"),
        )
        calculate = st.form_submit_button("Calculate risk", type="primary", width="stretch")

    if calculate:
        simulated_order = {
            "order_id": order_id,
            "patient_id": patient_id,
            "test_code": test_code,
            "test_category": test_category,
            "priority": priority_value,
            "order_time": datetime.now().isoformat(timespec="seconds"),
            "promised_completion_window_hours": promised,
            "elapsed_at_checkpoint_hours": elapsed,
            "expected_remaining_hours": remaining,
            "on_track_at_checkpoint": on_track,
        }
        st.session_state["simulated_alert"] = make_alert_item(simulated_order, opted_in)
        st.session_state["simulated_recipient"] = recipient

    if "simulated_alert" in st.session_state:
        alert = st.session_state["simulated_alert"]
        risk = alert["risk"]
        notification = alert["notification"]
        st.divider()
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Breach probability", f"{risk.breach_probability:.1%}")
        x2.metric("Risk level", risk.risk_level.upper())
        x3.metric("Projected slip", f"{risk.projected_slip_hours:+.2f} h")
        x4.metric("Notification", notification["status"])
        st.progress(risk.breach_probability)

        preview = build_email(
            [alert],
            "diagnostic-agent@local.demo",
            [st.session_state["simulated_recipient"]],
        )
        st.text_area("Alert email preview", preview.get_content(), height=300, disabled=True)
        send_col, smtp_col = st.columns(2)
        if send_col.button("Trigger local alert", type="primary", width="stretch"):
            path = save_email_to_outbox(preview)
            st.success(f"Local alert created: {path}")
        smtp_confirm = smtp_col.checkbox("I confirm SMTP delivery")
        if smtp_col.button("Send SMTP alert", width="stretch", disabled=not smtp_confirm):
            try:
                config = MailConfig.from_env()
                config.recipients = [st.session_state["simulated_recipient"]]
                smtp_message = build_email([alert], config.sender, config.recipients)
                send_email(smtp_message, config)
                st.success(f"SMTP alert sent to {config.recipients[0]}")
            except Exception as exc:
                st.error(f"SMTP alert failed: {exc}")

with tab_delivery:
    st.subheader("Delivery readiness")
    mail = MailConfig.from_env()
    status_rows = pd.DataFrame(
        [
            {"Setting": "SMTP host", "Configured": bool(mail.host)},
            {"Setting": "SMTP sender", "Configured": bool(mail.sender)},
            {"Setting": "SMTP recipients", "Configured": bool(mail.recipients)},
            {"Setting": "SMTP credentials", "Configured": bool(mail.username and mail.password)},
        ]
    )
    st.dataframe(status_rows, width="stretch", hide_index=True)
    st.code(
        "python alert_runner.py --send --max-alerts 25\n"
        "python watch_alerts.py --send --interval-seconds 300",
        language="bash",
    )
    st.info(
        "Use Trigger Lab for a safe local demonstration. Configure SMTP environment variables "
        "only when you are ready to deliver to an operations mailbox."
    )
