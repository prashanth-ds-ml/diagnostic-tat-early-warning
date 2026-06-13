import pandas as pd

from alert_runner import build_email, save_email_to_outbox, select_alerts


def test_select_alerts_filters_risk_and_deduplicates():
    orders = pd.DataFrame(
        [
            {
                "order_id": "ORD-HIGH",
                "patient_id": "PAT-1",
                "test_code": "CBC",
                "test_category": "hematology",
                "priority": "routine",
                "order_time": "2026-06-13T10:00:00",
                "promised_completion_window_hours": 4,
                "elapsed_at_checkpoint_hours": 2,
                "expected_remaining_hours": 4,
                "on_track_at_checkpoint": False,
            },
            {
                "order_id": "ORD-LOW",
                "patient_id": "PAT-2",
                "test_code": "CBC",
                "test_category": "hematology",
                "priority": "stat",
                "order_time": "2026-06-13T10:01:00",
                "promised_completion_window_hours": 4,
                "elapsed_at_checkpoint_hours": 1,
                "expected_remaining_hours": 1,
                "on_track_at_checkpoint": True,
            },
        ]
    )
    patients = pd.DataFrame(
        [
            {"patient_id": "PAT-1", "notification_opt_in": True},
            {"patient_id": "PAT-2", "notification_opt_in": False},
        ]
    )

    alerts = select_alerts(orders, patients, set(), 0.40, 25, True)
    assert [item["risk"].order_id for item in alerts] == ["ORD-HIGH"]
    assert select_alerts(orders, patients, {"ORD-HIGH"}, 0.40, 25, True) == []


def test_email_contains_operational_alert_details():
    orders = pd.DataFrame(
        [
            {
                "order_id": "ORD-HIGH",
                "patient_id": "PAT-1",
                "test_code": "CBC",
                "test_category": "hematology",
                "priority": "routine",
                "order_time": "2026-06-13T10:00:00",
                "promised_completion_window_hours": 4,
                "elapsed_at_checkpoint_hours": 2,
                "expected_remaining_hours": 4,
                "on_track_at_checkpoint": False,
            }
        ]
    )
    patients = pd.DataFrame([{"patient_id": "PAT-1", "notification_opt_in": True}])
    alerts = select_alerts(orders, patients, set(), 0.40, 25, True)
    email = build_email(alerts, "sender@example.com", ["ops@example.com"])
    assert "ORD-HIGH" in email.get_content()
    assert "Patient notification status: draft_pending_review" in email.get_content()
    assert email["To"] == "ops@example.com"


def test_email_can_be_saved_to_local_outbox(tmp_path):
    email = build_email([], "sender@example.com", ["ops@example.com"])
    path = save_email_to_outbox(email, tmp_path)
    assert path.exists()
    assert b"Diagnostic SLA alert" in path.read_bytes()
