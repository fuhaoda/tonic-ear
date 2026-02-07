from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_meta_success():
    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    payload = response.json()
    assert "genders" in payload
    assert "keys" in payload
    assert "temperaments" in payload
    assert "modules" in payload
    assert "difficulties" in payload


def test_create_session_success():
    response = client.post(
        "/api/v1/session",
        json={
            "moduleId": "M3-L2",
            "gender": "male",
            "key": "E",
            "temperament": "equal_temperament",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "sessionId" in payload
    assert len(payload["questions"]) == 20


def test_create_session_rejects_unknown_module():
    response = client.post(
        "/api/v1/session",
        json={
            "moduleId": "UNKNOWN",
            "gender": "male",
            "key": "C",
            "temperament": "equal_temperament",
        },
    )

    assert response.status_code == 400
    assert "Unknown module" in response.json()["detail"]


def test_create_session_rejects_invalid_key():
    response = client.post(
        "/api/v1/session",
        json={
            "moduleId": "M2-L1",
            "gender": "female",
            "key": "H",
            "temperament": "equal_temperament",
        },
    )

    assert response.status_code == 422
