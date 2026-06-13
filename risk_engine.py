from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DATA_DIR = Path(
    os.environ.get(
        "DIAGNOSTIC_DATA_DIR",
        APP_DIR,
    )
).resolve()


@dataclass
class RiskResult:
    order_id: str
    patient_id: str
    breach_probability: float
    risk_level: str
    projected_slip_hours: float
    hours_until_sla: float
    estimated_completion_time: str
    promised_completion_time: str
    recommended_action: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, value))))


def score_order(order: dict[str, Any]) -> RiskResult:
    elapsed = float(order["elapsed_at_checkpoint_hours"])
    remaining = float(order["expected_remaining_hours"])
    promised = max(float(order["promised_completion_window_hours"]), 0.1)
    projected_slip = elapsed + remaining - promised
    projected_slip_ratio = projected_slip / promised

    priority_adjustment = {"routine": 0.10, "urgent": 0.0, "stat": -0.10}.get(
        str(order.get("priority", "")).lower(), 0.0
    )
    probability = _sigmoid(3.7 * projected_slip_ratio + priority_adjustment)

    # The checkpoint flag is a transparent operational rule, not a trained feature.
    on_track = _as_bool(order.get("on_track_at_checkpoint", projected_slip <= 0))
    if not on_track:
        probability = max(probability, 0.70)

    if probability >= 0.80:
        risk_level = "critical"
        action = "Escalate to diagnostics coordinator and draft patient notification."
    elif probability >= 0.60:
        risk_level = "high"
        action = "Review queue position and prepare a patient notification."
    elif probability >= 0.40:
        risk_level = "medium"
        action = "Monitor at the next processing checkpoint."
    else:
        risk_level = "low"
        action = "Continue standard monitoring."

    order_time = pd.Timestamp(order["order_time"]).to_pydatetime()
    checkpoint_time = order_time + timedelta(hours=elapsed)
    promised_time = order_time + timedelta(hours=promised)
    estimated_time = checkpoint_time + timedelta(hours=remaining)

    reasons = [
        f"Projected completion is {projected_slip:+.2f} hours relative to the SLA.",
        f"{elapsed / promised:.0%} of the promised window was used by the checkpoint.",
        f"Checkpoint status is {'on track' if on_track else 'off track'}.",
    ]
    if str(order.get("priority", "")).lower() == "routine":
        reasons.append("Routine orders have less operational priority than urgent/stat orders.")

    return RiskResult(
        order_id=str(order["order_id"]),
        patient_id=str(order["patient_id"]),
        breach_probability=round(probability, 4),
        risk_level=risk_level,
        projected_slip_hours=round(projected_slip, 2),
        hours_until_sla=round((promised_time - checkpoint_time).total_seconds() / 3600, 2),
        estimated_completion_time=estimated_time.isoformat(timespec="minutes"),
        promised_completion_time=promised_time.isoformat(timespec="minutes"),
        recommended_action=action,
        reasons=reasons,
    )


def draft_notification(order: dict[str, Any], risk: RiskResult, opted_in: bool) -> dict[str, Any]:
    if not opted_in:
        return {
            "eligible": False,
            "status": "blocked_no_consent",
            "message": None,
            "requires_staff_approval": True,
        }

    test_name = str(order["test_code"]).replace("_", " ")
    message = (
        f"Your {test_name} is taking longer than originally expected. "
        f"Our current estimated completion time is {risk.estimated_completion_time}. "
        "We apologize for the delay and will notify you when the report is ready."
    )
    return {
        "eligible": True,
        "status": "draft_pending_review",
        "message": message,
        "requires_staff_approval": True,
    }


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"Diagnostic data directory not found: {DATA_DIR}. "
            "Use the bundled synthetic data or set DIAGNOSTIC_DATA_DIR."
        )
    orders = pd.read_csv(DATA_DIR / "synthetic_diagnostic_orders.csv")
    patients = pd.read_csv(DATA_DIR / "synthetic_op_patients.csv")
    resources = pd.read_csv(DATA_DIR / "synthetic_diagnostic_resources.csv")
    return orders, patients, resources


def enrich_with_resource_context(orders: pd.DataFrame, resources: pd.DataFrame) -> pd.DataFrame:
    result = orders.copy()
    result["resource_date"] = pd.to_datetime(result["order_time"]).dt.date.astype(str)
    context = resources.copy()
    context["resource_date"] = context["resource_date"].astype(str)
    context["capacity_load_ratio"] = (
        context["actual_throughput_orders"] / context["theoretical_capacity_orders"].clip(lower=1)
    )
    return result.merge(
        context[
            [
                "resource_category",
                "resource_date",
                "capacity_load_ratio",
                "downtime_minutes",
            ]
        ],
        left_on=["test_category", "resource_date"],
        right_on=["resource_category", "resource_date"],
        how="left",
    )


def score_dataframe(orders: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for order in orders.to_dict(orient="records"):
        rows.append(score_order(order).to_dict())
    return pd.DataFrame(rows)
