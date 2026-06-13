from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


def simulated_order():
    return {
        "order_id": "LOCAL-API-TEST",
        "patient_id": "LOCAL-PATIENT",
        "test_code": "CBC",
        "test_category": "hematology",
        "priority": "routine",
        "order_time": "2026-06-13T10:00:00",
        "promised_completion_window_hours": 4,
        "elapsed_at_checkpoint_hours": 2,
        "expected_remaining_hours": 4,
        "on_track_at_checkpoint": False,
        "notification_opt_in": True,
        "recipient": "ops@example.com",
    }


def test_dashboard_and_queue_endpoints():
    assert client.get("/dashboard").status_code == 200
    queue = client.get("/queue?limit=2").json()
    assert len(queue) == 2
    assert "test_code" in queue[0]


def test_simulate_and_local_trigger():
    simulation = client.post("/simulate", json=simulated_order())
    assert simulation.status_code == 200
    assert simulation.json()["risk"]["breach_probability"] >= 0.7
    trigger = client.post(
        "/trigger", json={"order": simulated_order(), "delivery": "local"}
    )
    assert trigger.status_code == 200
    assert trigger.json()["status"] == "saved_local"
