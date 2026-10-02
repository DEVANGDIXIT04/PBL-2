from datetime import datetime, timedelta

from app.db.models import Transaction
from tests.conftest import auth_header, category_id


def test_spike_is_flagged_with_a_reason(client, db_session):
    headers = auth_header(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    food = category_id(client, headers, "Food")
    start = datetime(2026, 1, 1, 13, 0, 0)
    for offset in range(36):
        db_session.add(
            Transaction(
                user_id=me["id"],
                category_id=food,
                amount=400,
                type="expense",
                description="Lunch",
                merchant="Swiggy",
                txn_date=start + timedelta(days=offset),
            )
        )
    spike = Transaction(
        user_id=me["id"],
        category_id=food,
        amount=20000,
        type="expense",
        description="Spike",
        merchant="UNKNOWN-WIRE",
        txn_date=start + timedelta(days=40),
    )
    db_session.add(spike)
    db_session.commit()
    db_session.refresh(spike)

    detected = client.post("/api/v1/anomalies/detect", headers=headers, json={"retrain": True})
    assert detected.status_code == 200, detected.text
    assert detected.json()["anomalies"] >= 1

    listing = client.get("/api/v1/anomalies", headers=headers)
    assert listing.status_code == 200
    flagged_ids = {row["id"] for row in listing.json()}
    assert spike.id in flagged_ids
    reason = next(row["anomaly_reason"] for row in listing.json() if row["id"] == spike.id)
    assert reason
    assert "Food" in reason or "merchant" in reason.lower() or "amount" in reason.lower()

    labelled = client.patch(
        f"/api/v1/transactions/{spike.id}/anomaly-label",
        headers=headers,
        json={"is_anomaly": True},
    )
    assert labelled.status_code == 200
    assert labelled.json()["anomaly_label_manual"] is True
    other = auth_header(client, "grace@example.com")
    hidden = client.patch(
        f"/api/v1/transactions/{spike.id}/anomaly-label",
        headers=other,
        json={"is_anomaly": False},
    )
    assert hidden.status_code == 404


def test_forecast_excludes_the_outlier(client, db_session):
    headers = auth_header(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    food = category_id(client, headers, "Food")
    for month in range(1, 11):
        amount = 9500 if month == 8 else 3000
        db_session.add(
            Transaction(
                user_id=me["id"],
                category_id=food,
                amount=amount,
                type="expense",
                description="Food budget",
                merchant="Swiggy",
                txn_date=datetime(2026, month, 5, 12, 0, 0),
                is_anomaly=amount == 9500,
                anomaly_reason="9.5x the usual Food spend" if amount == 9500 else None,
                anomaly_score=1.2 if amount == 9500 else -0.1,
            )
        )
    db_session.commit()
    response = client.get(
        "/api/v1/forecast?horizon=2&granularity=monthly&by_category=true", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    overall = body["overall"]
    assert overall["next_raw"] > overall["next_adjusted"]
    assert "2026-08" in overall["excluded_periods"]
    assert "Food" in body["by_category"]
    assert len(overall["lower"]) == 2
    assert overall["lower"][0]["value"] <= overall["forecast_adjusted"][0]["value"]
