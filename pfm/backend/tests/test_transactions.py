from datetime import datetime

from app.db.models import Transaction
from tests.conftest import auth_header, category_id


def test_transaction_crud_and_filters(client):
    headers = auth_header(client)
    food = category_id(client, headers, "Food")
    salary = category_id(client, headers, "Salary")
    created = client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "category_id": food,
            "amount": 250.5,
            "type": "expense",
            "description": "Lunch",
            "merchant": "Swiggy",
            "txn_date": "2026-03-02T13:00:00",
        },
    )
    assert created.status_code == 201, created.text
    txn_id = created.json()["id"]
    assert created.json()["amount"] == 250.5

    client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "category_id": salary,
            "amount": 80000,
            "type": "income",
            "description": "Pay",
            "merchant": "Employer",
            "txn_date": "2026-03-01T10:00:00",
        },
    )
    listed = client.get("/api/v1/transactions?txn_type=expense&sort=amount", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["merchant"] == "Swiggy"

    updated = client.patch(
        f"/api/v1/transactions/{txn_id}",
        headers=headers,
        json={"amount": 300, "description": "Dinner"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 300

    fetched = client.get(f"/api/v1/transactions/{txn_id}", headers=headers)
    assert fetched.status_code == 200
    deleted = client.delete(f"/api/v1/transactions/{txn_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/transactions/{txn_id}", headers=headers).status_code == 404


def test_users_cannot_read_each_others_transactions(client):
    ada = auth_header(client, "ada@example.com")
    food = category_id(client, ada, "Food")
    created = client.post(
        "/api/v1/transactions",
        headers=ada,
        json={
            "category_id": food,
            "amount": 100,
            "type": "expense",
            "description": "Mine",
            "merchant": "Cafe",
            "txn_date": "2026-04-04T12:00:00",
        },
    )
    txn_id = created.json()["id"]
    grace = auth_header(client, "grace@example.com")
    assert client.get(f"/api/v1/transactions/{txn_id}", headers=grace).status_code == 404
    listed = client.get("/api/v1/transactions", headers=grace)
    assert listed.json()["total"] == 0
    assert (
        client.patch(
            f"/api/v1/transactions/{txn_id}", headers=grace, json={"amount": 5}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/transactions/{txn_id}", headers=grace).status_code == 404


def test_csv_import_reports_rejected_rows(client):
    headers = auth_header(client)
    csv_text = (
        "date,amount,type,category,description,merchant\n"
        "2026-01-05,250,expense,Food,Lunch,Swiggy\n"
        "not-a-date,10,expense,Food,Bad,X\n"
        "2026-01-06,-4,expense,Food,Negative,X\n"
        "2026-01-07,999,income,Food,Wrong type,X\n"
    )
    response = client.post(
        "/api/v1/transactions/import-csv",
        headers=headers,
        files={"file": ("tx.csv", csv_text, "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 1
    assert len(body["rejected"]) == 3
    listed = client.get("/api/v1/transactions", headers=headers)
    assert listed.json()["total"] == 1


def test_category_and_budget_crud(client):
    headers = auth_header(client)
    created = client.post(
        "/api/v1/categories", headers=headers, json={"name": "Coffee", "type": "expense"}
    )
    assert created.status_code == 201, created.text
    category_id_value = created.json()["id"]
    food = category_id(client, headers, "Food")
    assert (
        client.patch(
            f"/api/v1/categories/{food}", headers=headers, json={"name": "Meals"}
        ).status_code
        == 403
    )
    renamed = client.patch(
        f"/api/v1/categories/{category_id_value}", headers=headers, json={"name": "Cafe"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Cafe"

    budget = client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"category_id": category_id_value, "month": "2026-05", "limit_amount": 2000},
    )
    assert budget.status_code == 201, budget.text
    budget_id = budget.json()["id"]
    client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "category_id": category_id_value,
            "amount": 500,
            "type": "expense",
            "description": "Latte",
            "merchant": "CCD",
            "txn_date": "2026-05-02T09:00:00",
        },
    )
    listed = client.get("/api/v1/budgets?month=2026-05", headers=headers)
    assert listed.json()[0]["spent"] == 500
    assert listed.json()[0]["usage_ratio"] == 0.25
    other = auth_header(client, "grace@example.com")
    assert client.delete(f"/api/v1/budgets/{budget_id}", headers=other).status_code == 404
    assert (
        client.delete(f"/api/v1/categories/{category_id_value}", headers=headers).status_code == 409
    )
    txn_id = client.get("/api/v1/transactions", headers=headers).json()["items"][0]["id"]
    assert client.delete(f"/api/v1/transactions/{txn_id}", headers=headers).status_code == 204
    assert (
        client.delete(f"/api/v1/categories/{category_id_value}", headers=headers).status_code == 204
    )


def test_summary_math(client, db_session):
    headers = auth_header(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    salary = category_id(client, headers, "Salary")
    food = category_id(client, headers, "Food")
    db_session.add_all(
        [
            Transaction(
                user_id=me["id"],
                category_id=salary,
                amount=10000,
                type="income",
                description="Pay",
                merchant="Work",
                txn_date=datetime(2026, 6, 1, 10, 0, 0),
            ),
            Transaction(
                user_id=me["id"],
                category_id=food,
                amount=2500,
                type="expense",
                description="Food",
                merchant="Swiggy",
                txn_date=datetime(2026, 6, 3, 13, 0, 0),
                is_anomaly=True,
            ),
        ]
    )
    db_session.commit()
    client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"category_id": food, "month": "2026-06", "limit_amount": 5000},
    )
    summary = client.get("/api/v1/reports/summary?month=2026-06", headers=headers)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["income"] == 10000
    assert body["expense"] == 2500
    assert body["savings"] == 7500
    assert body["savings_rate"] == 0.75
    assert body["anomaly_count"] == 1
    assert body["top_categories"][0]["category"] == "Food"
    assert body["budget_usage"][0]["usage_ratio"] == 0.5
    assert len(body["trend"]) == 6
