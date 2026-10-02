import pytest


# --- Phase 1: request validation (400) ---


def test_missing_question_returns_400(client):
    response = client.post("/query", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "question is required"


@pytest.mark.parametrize("question", ["", "   ", "\n\t "])
def test_empty_or_whitespace_question_returns_400(client, question):
    response = client.post("/query", json={"question": question})

    assert response.status_code == 400
    assert response.json()["detail"] == "question is required"


# --- Placeholder response ---


def test_valid_question_returns_placeholder(client):
    response = client.post("/query", json={"question": "Where did I leave my charger?"})

    assert response.status_code == 200
    assert response.json() == {"matched_photo_id": None, "message": "not yet implemented"}
