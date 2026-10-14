import os

os.environ["TESTING"] = "1"
os.environ.setdefault("DATABASE_URL", "postgresql://unused")

import pytest
from app import app, limiter


@pytest.fixture
def client():
    app.config["TESTING"] = True
    limiter.reset()
    return app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_generate_requires_fields(client):
    r = client.post("/generate", json={})
    assert r.status_code == 400


def test_rejects_non_text_input(client):
    r = client.post("/generate", json={"product_name": 123, "description": "A mug"})
    assert r.status_code == 400


def test_rejects_too_long_description(client):
    r = client.post("/generate", json={"product_name": "Mug", "description": "x" * 601})
    assert r.status_code == 400


def test_rate_limit_kicks_in(client):
    codes = [client.post("/generate", json={}).status_code for _ in range(6)]
    assert codes[:5] == [400] * 5
    assert codes[5] == 429