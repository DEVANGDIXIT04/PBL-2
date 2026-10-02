from tests.conftest import auth_header, register


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert client.get("/").status_code == 200


def test_register_login_me_refresh(client):
    tokens = register(client, "person@example.com", "password123")
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "person@example.com"
    assert "hashed_password" not in me.json()

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    rejected = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert rejected.status_code == 401
    assert rejected.json()["code"] == "unauthorized"


def test_duplicate_email_and_bad_password(client):
    register(client, "person@example.com", "password123")
    again = client.post(
        "/api/v1/auth/register", json={"email": "person@example.com", "password": "password123"}
    )
    assert again.status_code == 409
    bad = client.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": "wrong-pass"}
    )
    assert bad.status_code == 401


def test_auth_required_and_validation_shape(client):
    missing = client.get("/api/v1/transactions")
    assert missing.status_code == 401
    assert missing.json()["code"] == "unauthorized"
    invalid = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": "short"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"


def test_login_after_register(client):
    register(client, "person@example.com", "password123")
    response = client.post(
        "/api/v1/auth/login", json={"email": "Person@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    headers = auth_header(client, "other@example.com")
    assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == "other@example.com"
