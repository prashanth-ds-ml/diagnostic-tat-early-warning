from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException

from risk_engine import draft_notification, load_data, score_order


app = FastAPI(
    title="Diagnostic TAT Early Warning Agent",
    description="Local prototype for Problem 9: predict SLA breaches at checkpoint.",
    version="0.1.0",
)


@lru_cache(maxsize=1)
def data():
    orders, patients, resources = load_data()
    return (
        orders.set_index("order_id", drop=False),
        patients.set_index("patient_id", drop=False),
        resources,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "data_source": "SYNTHETIC"}


@app.get("/orders/{order_id}/risk")
def order_risk(order_id: str) -> dict:
    orders, patients, _ = data()
    if order_id not in orders.index:
        raise HTTPException(status_code=404, detail="Order not found")

    order = orders.loc[order_id].to_dict()
    risk = score_order(order)
    opted_in = bool(patients.loc[order["patient_id"], "notification_opt_in"])
    return {
        "risk": risk.to_dict(),
        "notification": draft_notification(order, risk, opted_in),
        "data_source": "SYNTHETIC",
    }


@app.get("/queue")
def queue(limit: int = 25, minimum_probability: float = 0.4) -> list[dict]:
    orders, _, _ = data()
    recent = orders.sort_values("order_time", ascending=False).head(5000)
    scored = [score_order(row).to_dict() for row in recent.to_dict(orient="records")]
    scored = [row for row in scored if row["breach_probability"] >= minimum_probability]
    return sorted(scored, key=lambda row: row["breach_probability"], reverse=True)[:limit]
