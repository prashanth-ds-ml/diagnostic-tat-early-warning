from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from alert_runner import (
    MailConfig,
    build_email,
    list_text_messages,
    save_email_to_outbox,
    save_text_message,
    send_email,
)
from risk_engine import (
    derive_checkpoint_order,
    draft_notification,
    enrich_with_resource_context,
    load_data,
    score_dataframe,
    score_order,
)


app = FastAPI(
    title="Diagnostic TAT Early Warning Agent",
    description="Predict diagnostic SLA breaches at the interim checkpoint.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulatedOrder(BaseModel):
    order_id: str = "LOCAL-DEMO-001"
    patient_id: str = "LOCAL-PATIENT"
    test_code: str = "CBC"
    test_category: str = "hematology"
    priority: str = "routine"
    order_time: str
    promised_completion_window_hours: float = Field(gt=0)
    elapsed_at_checkpoint_hours: float = Field(ge=0)
    expected_remaining_hours: float = Field(ge=0)
    on_track_at_checkpoint: bool = False
    notification_opt_in: bool = True
    recipient: str = "diagnostics-operations@example.com"


class TriggerRequest(BaseModel):
    order: SimulatedOrder
    delivery: str = "local"


class LifecycleOrder(BaseModel):
    order_id: str = "LOCAL-DEMO-001"
    patient_id: str = "LOCAL-PATIENT"
    test_code: str
    test_category: str
    priority: str = "routine"
    order_time: str
    specimen_received_time: str
    test_started_time: str
    promised_completion_window_hours: float | None = Field(default=None, gt=0)
    notification_opt_in: bool = True


@lru_cache(maxsize=1)
def data():
    orders, patients, resources = load_data()
    recent = orders.sort_values("order_time", ascending=False).head(5000)
    enriched = enrich_with_resource_context(recent, resources)
    scored = score_dataframe(enriched)
    queue = enriched.merge(scored, on=["order_id", "patient_id"])
    return (
        orders.set_index("order_id", drop=False),
        patients.set_index("patient_id", drop=False),
        resources,
        queue,
    )


def create_alert(order: dict[str, Any], opted_in: bool) -> dict[str, Any]:
    risk = score_order(order)
    return {
        "order": order,
        "risk": risk.to_dict(),
        "notification": draft_notification(order, risk, opted_in),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "data_source": "SYNTHETIC"}


@app.get("/dashboard")
def dashboard(minimum_probability: float = 0.4) -> dict[str, Any]:
    _, patients, _, queue = data()
    alerts = queue[queue["breach_probability"] >= minimum_probability]
    opted_in_ids = set(patients[patients["notification_opt_in"].astype(bool)].index)
    risk_mix = alerts["risk_level"].value_counts().to_dict()
    resource_pressure = (
        alerts.groupby("test_category")["capacity_load_ratio"]
        .mean()
        .sort_values(ascending=False)
        .head(7)
        .round(3)
        .to_dict()
    )
    return {
        "metrics": {
            "orders_monitored": len(queue),
            "active_alerts": len(alerts),
            "critical": int(alerts["risk_level"].eq("critical").sum()),
            "off_track": int((~queue["on_track_at_checkpoint"].astype(bool)).sum()),
            "consent_eligible": int(alerts["patient_id"].isin(opted_in_ids).sum()),
        },
        "risk_mix": risk_mix,
        "resource_pressure": resource_pressure,
    }


@app.get("/options")
def options() -> dict[str, list[str]]:
    _, _, _, queue = data()
    return {
        "test_codes": sorted(queue["test_code"].unique().tolist()),
        "test_categories": sorted(queue["test_category"].unique().tolist()),
        "priorities": ["routine", "urgent", "stat"],
    }


@app.get("/orders/{order_id}/risk")
def order_risk(order_id: str) -> dict[str, Any]:
    orders, patients, _, _ = data()
    if order_id not in orders.index:
        raise HTTPException(status_code=404, detail="Order not found")
    order = orders.loc[order_id].to_dict()
    return create_alert(order, bool(patients.loc[order["patient_id"], "notification_opt_in"]))


@app.get("/queue")
def queue(limit: int = 100, minimum_probability: float = 0.4) -> list[dict[str, Any]]:
    _, patients, _, scored_queue = data()
    selected = scored_queue[scored_queue["breach_probability"] >= minimum_probability].copy()
    selected = selected.sort_values("breach_probability", ascending=False).head(limit)
    selected["notification_opt_in"] = selected["patient_id"].map(
        patients["notification_opt_in"].astype(bool)
    )
    columns = [
        "order_id",
        "patient_id",
        "test_code",
        "test_category",
        "priority",
        "order_time",
        "on_track_at_checkpoint",
        "breach_probability",
        "risk_level",
        "projected_slip_hours",
        "hours_until_sla",
        "promised_completion_time",
        "estimated_completion_time",
        "recommended_action",
        "capacity_load_ratio",
        "downtime_minutes",
        "notification_opt_in",
    ]
    return selected[columns].where(selected[columns].notna(), None).to_dict(orient="records")


@app.post("/simulate")
def simulate(order: SimulatedOrder) -> dict[str, Any]:
    return create_alert(order.model_dump(exclude={"notification_opt_in", "recipient"}), order.notification_opt_in)


@app.post("/simulate-lifecycle")
def simulate_lifecycle(order: LifecycleOrder) -> dict[str, Any]:
    try:
        derived = derive_checkpoint_order(order.model_dump(exclude={"notification_opt_in"}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    alert = create_alert(derived, order.notification_opt_in)
    alert["derived_features"] = {
        "order_to_specimen_hours": derived["order_to_specimen_hours"],
        "specimen_to_start_hours": derived["specimen_to_start_hours"],
        "elapsed_at_checkpoint_hours": round(derived["elapsed_at_checkpoint_hours"], 2),
        "expected_remaining_hours": round(derived["expected_remaining_hours"], 2),
        "promised_completion_window_hours": round(
            derived["promised_completion_window_hours"], 2
        ),
        "on_track_at_checkpoint": derived["on_track_at_checkpoint"],
    }
    return alert


@app.post("/trigger-text")
def trigger_text(order: LifecycleOrder) -> dict[str, Any]:
    if not order.notification_opt_in:
        raise HTTPException(status_code=400, detail="Patient notification consent is required.")
    try:
        derived = derive_checkpoint_order(order.model_dump(exclude={"notification_opt_in"}))
        risk = score_order(derived)
        notification = draft_notification(derived, risk, True)
        path = save_text_message(derived, risk, notification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "local_text_delivered",
        "path": str(path),
        "message": list_text_messages()[0],
    }


@app.get("/messages")
def messages() -> list[dict[str, Any]]:
    return list_text_messages()


@app.post("/trigger")
def trigger(request: TriggerRequest) -> dict[str, Any]:
    order_data = request.order.model_dump(exclude={"notification_opt_in", "recipient"})
    risk = score_order(order_data)
    alert = {
        "order": order_data,
        "risk": risk,
        "notification": draft_notification(order_data, risk, request.order.notification_opt_in),
    }
    recipient = request.order.recipient
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient is required")

    if request.delivery == "local":
        message = build_email([alert], "diagnostic-agent@local.demo", [recipient])
        path = save_email_to_outbox(message)
        return {"status": "saved_local", "path": str(path), "recipient": recipient}
    if request.delivery == "smtp":
        config = MailConfig.from_env()
        config.recipients = [recipient]
        message = build_email([alert], config.sender, config.recipients)
        try:
            send_email(message, config)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "sent_smtp", "recipient": recipient}
    raise HTTPException(status_code=400, detail="Delivery must be local or smtp")


@app.get("/delivery-status")
def delivery_status() -> dict[str, bool]:
    config = MailConfig.from_env()
    return {
        "smtp_host": bool(config.host),
        "smtp_sender": bool(config.sender),
        "smtp_recipients": bool(config.recipients),
        "smtp_credentials": bool(config.username and config.password),
        "default_recipient": os.environ.get("ALERT_RECIPIENTS", ""),
    }
