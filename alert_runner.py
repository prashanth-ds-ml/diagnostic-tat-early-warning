from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pandas as pd

from risk_engine import draft_notification, load_data, score_order


APP_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = APP_DIR / "runtime" / "alert_state.json"
DEFAULT_OUTBOX = APP_DIR / "runtime" / "outbox"


@dataclass
class MailConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipients: list[str]
    use_ssl: bool
    use_starttls: bool

    @classmethod
    def from_env(cls) -> "MailConfig":
        recipients = [
            value.strip()
            for value in os.environ.get("ALERT_RECIPIENTS", "").split(",")
            if value.strip()
        ]
        return cls(
            host=os.environ.get("SMTP_HOST", ""),
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USERNAME", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            sender=os.environ.get("SMTP_SENDER", os.environ.get("SMTP_USERNAME", "")),
            recipients=recipients,
            use_ssl=os.environ.get("SMTP_USE_SSL", "false").lower() == "true",
            use_starttls=os.environ.get("SMTP_USE_STARTTLS", "true").lower() == "true",
        )

    def validate(self) -> None:
        missing = []
        if not self.host:
            missing.append("SMTP_HOST")
        if not self.sender:
            missing.append("SMTP_SENDER")
        if not self.recipients:
            missing.append("ALERT_RECIPIENTS")
        if missing:
            raise ValueError(f"Missing required mail configuration: {', '.join(missing)}")


def load_alerted_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("alerted_order_ids", []))


def save_alerted_ids(path: Path, alerted_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "alerted_order_ids": sorted(alerted_ids),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def select_alerts(
    orders: pd.DataFrame,
    patients: pd.DataFrame,
    already_alerted: set[str],
    threshold: float,
    max_alerts: int,
    latest_date_only: bool,
) -> list[dict[str, Any]]:
    candidates = orders.copy()
    candidates["order_date"] = pd.to_datetime(candidates["order_time"]).dt.date
    if latest_date_only:
        candidates = candidates[candidates["order_date"] == candidates["order_date"].max()]

    patients_by_id = patients.set_index("patient_id")
    alerts = []
    for order in candidates.sort_values("order_time", ascending=False).to_dict(orient="records"):
        if str(order["order_id"]) in already_alerted:
            continue
        risk = score_order(order)
        if risk.breach_probability < threshold:
            continue
        opted_in = bool(patients_by_id.loc[order["patient_id"], "notification_opt_in"])
        alerts.append(
            {
                "order": order,
                "risk": risk,
                "notification": draft_notification(order, risk, opted_in),
            }
        )

    alerts.sort(key=lambda item: item["risk"].breach_probability, reverse=True)
    return alerts[:max_alerts]


def build_email(alerts: list[dict[str, Any]], sender: str, recipients: list[str]) -> EmailMessage:
    critical = sum(item["risk"].risk_level == "critical" for item in alerts)
    message = EmailMessage()
    message["Subject"] = f"Diagnostic SLA alert: {len(alerts)} at-risk orders ({critical} critical)"
    message["From"] = sender
    message["To"] = ", ".join(recipients)

    lines = [
        "Automated diagnostic turnaround early-warning alert",
        "",
        f"At-risk orders: {len(alerts)}",
        f"Critical orders: {critical}",
        "Alert threshold: configured checkpoint breach probability",
        "",
    ]
    for item in alerts:
        order = item["order"]
        risk = item["risk"]
        notification = item["notification"]
        lines.extend(
            [
                f"Order: {risk.order_id}",
                f"Test: {order['test_code']} ({order['test_category']})",
                f"Priority: {order['priority']}",
                f"Risk: {risk.breach_probability:.1%} ({risk.risk_level})",
                f"Projected slip: {risk.projected_slip_hours:+.2f} hours",
                f"Promised completion: {risk.promised_completion_time}",
                f"Estimated completion: {risk.estimated_completion_time}",
                f"Patient notification status: {notification['status']}",
                f"Recommended action: {risk.recommended_action}",
                "Reasons: " + " | ".join(risk.reasons),
                "-" * 72,
            ]
        )
    lines.extend(
        [
            "",
            "Synthetic-data prototype. Verify the order in the clinical system before action.",
        ]
    )
    message.set_content("\n".join(lines))
    return message


def send_email(message: EmailMessage, config: MailConfig) -> None:
    config.validate()
    if config.use_ssl:
        with smtplib.SMTP_SSL(
            config.host, config.port, context=ssl.create_default_context(), timeout=30
        ) as smtp:
            if config.username:
                smtp.login(config.username, config.password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        if config.use_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if config.username:
            smtp.login(config.username, config.password)
        smtp.send_message(message)


def save_email_to_outbox(message: EmailMessage, outbox: Path = DEFAULT_OUTBOX) -> Path:
    outbox.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = outbox / f"diagnostic-alert-{timestamp}.eml"
    path.write_bytes(message.as_bytes())
    return path


def run(
    dry_run: bool,
    threshold: float,
    max_alerts: int,
    latest_date_only: bool,
    state_file: Path,
) -> int:
    orders, patients, _ = load_data()
    alerted_ids = load_alerted_ids(state_file)
    alerts = select_alerts(
        orders, patients, alerted_ids, threshold, max_alerts, latest_date_only
    )
    if not alerts:
        print("No new at-risk orders to alert.")
        return 0

    config = MailConfig.from_env()
    message = build_email(alerts, config.sender or "dry-run@example.invalid", config.recipients)
    if dry_run:
        print(message)
        print(f"\nDRY RUN: {len(alerts)} alerts selected; no email sent.")
        return 0

    send_email(message, config)
    alerted_ids.update(item["risk"].order_id for item in alerts)
    save_alerted_ids(state_file, alerted_ids)
    print(f"Sent {len(alerts)} alerts to {', '.join(config.recipients)}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Score orders and email new risk alerts.")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send email. Without this flag the runner is always a dry run.",
    )
    parser.add_argument("--threshold", type=float, default=0.40)
    parser.add_argument("--max-alerts", type=int, default=25)
    parser.add_argument("--all-dates", action="store_true")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    args = parser.parse_args()
    return run(
        dry_run=not args.send,
        threshold=args.threshold,
        max_alerts=args.max_alerts,
        latest_date_only=not args.all_dates,
        state_file=args.state_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
