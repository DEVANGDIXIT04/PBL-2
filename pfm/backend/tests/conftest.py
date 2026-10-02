import os
import tempfile

# Environment must be set before the application module builds its engine.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["MODEL_DIR"] = tempfile.mkdtemp(prefix="pfm-models-")

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register(
    client: TestClient, email: str = "ada@example.com", password: str = "password123"
) -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def auth_header(
    client: TestClient, email: str = "ada@example.com", password: str = "password123"
) -> dict[str, str]:
    tokens = register(client, email, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def category_id(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.get("/api/v1/categories", headers=headers)
    assert response.status_code == 200, response.text
    for row in response.json():
        if row["name"] == name:
            return int(row["id"])
    raise AssertionError(f"missing category {name}")
