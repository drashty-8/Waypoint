import pytest


QUESTION = "Where did I leave my charger?"


@pytest.fixture
def candidate_rows(fake_supabase):
    """Return a function that sets the rows the candidate photo query gets back.

    The fake doesn't filter or sort, so each test passes rows exactly as
    Supabase would return them: only complete photos, newest first.
    """
    def set_rows(rows):
        photos_query = fake_supabase.tables["photos"].select.return_value.eq.return_value.order.return_value
        photos_query.execute.return_value.data = rows

    return set_rows


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


# --- Phase 2: candidate gathering ---


def test_no_complete_photos_returns_empty_list(client, candidate_rows):
    candidate_rows([])

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == []


def test_only_complete_photos_are_requested(client, fake_supabase, candidate_rows):
    candidate_rows([])

    client.post("/query", json={"question": QUESTION})

    photos_table = fake_supabase.tables["photos"]
    photos_table.select.return_value.eq.assert_called_once_with("tagging_status", "complete")


def test_photo_with_beacon_gets_its_room_name(client, candidate_rows):
    candidate_rows([
        {
            "id": 1,
            "description": "A phone charger on a desk",
            "captured_at": "2026-09-26T14:00:00+00:00",
            "beacons": {"room_name": "Bedroom"},
        },
    ])

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "description": "A phone charger on a desk",
            "room_name": "Bedroom",
            "captured_at": "2026-09-26T14:00:00+00:00",
        },
    ]


def test_photo_without_beacon_gets_location_unknown(client, candidate_rows):
    candidate_rows([
        {
            "id": 2,
            "description": "Keys on a kitchen counter",
            "captured_at": "2026-09-26T14:00:00+00:00",
            "beacons": None,
        },
    ])

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json()[0]["room_name"] == "Location unknown"


def test_candidates_are_most_recent_first(client, fake_supabase, candidate_rows):
    # The sorting itself happens in the database, so check that the query
    # asks for newest first and that the endpoint keeps that order.
    candidate_rows([
        {"id": 3, "description": "newest", "captured_at": "2026-09-28T09:00:00+00:00", "beacons": None},
        {"id": 1, "description": "middle", "captured_at": "2026-09-27T09:00:00+00:00", "beacons": None},
        {"id": 2, "description": "oldest", "captured_at": "2026-09-26T09:00:00+00:00", "beacons": None},
    ])

    response = client.post("/query", json={"question": QUESTION})

    photos_filter = fake_supabase.tables["photos"].select.return_value.eq.return_value
    photos_filter.order.assert_called_once_with("captured_at", desc=True)

    ids = [photo["id"] for photo in response.json()]
    assert ids == [3, 1, 2]


def test_candidate_lookup_failure_returns_500(client, fake_supabase):
    photos_query = fake_supabase.tables["photos"].select.return_value.eq.return_value.order.return_value
    photos_query.execute.side_effect = Exception("database down")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not load photos"
