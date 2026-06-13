from risk_engine import derive_checkpoint_order, draft_notification, score_order


ORDER = {
    "order_id": "ORD-TEST",
    "patient_id": "PAT-TEST",
    "test_code": "CBC",
    "priority": "routine",
    "order_time": "2026-06-13T10:00:00",
    "promised_completion_window_hours": 4,
    "elapsed_at_checkpoint_hours": 2,
    "expected_remaining_hours": 4,
    "on_track_at_checkpoint": False,
}


def test_off_track_order_is_high_risk():
    result = score_order(ORDER)
    assert result.breach_probability >= 0.70
    assert result.projected_slip_hours == 2
    assert result.risk_level in {"high", "critical"}


def test_notification_requires_consent_and_review():
    risk = score_order(ORDER)
    blocked = draft_notification(ORDER, risk, opted_in=False)
    allowed = draft_notification(ORDER, risk, opted_in=True)
    assert blocked["status"] == "blocked_no_consent"
    assert allowed["status"] == "draft_pending_review"
    assert allowed["requires_staff_approval"] is True


def test_lifecycle_score_is_calibrated_and_increases_with_delay():
    base = {
        "order_id": "ORD-LIFECYCLE",
        "patient_id": "PAT-TEST",
        "test_code": "CBC",
        "test_category": "hematology",
        "priority": "routine",
        "order_time": "2026-06-13T08:00:00",
        "specimen_received_time": "2026-06-13T09:00:00",
        "promised_completion_window_hours": 4,
    }
    early = derive_checkpoint_order({**base, "test_started_time": "2026-06-13T09:30:00"})
    late = derive_checkpoint_order({**base, "test_started_time": "2026-06-13T12:00:00"})
    early_risk = score_order(early)
    late_risk = score_order(late)
    assert late_risk.breach_probability > early_risk.breach_probability
    assert late_risk.score_method == "historical test-start calibration"
    assert late_risk.historical_peer_count > 0
