from types import SimpleNamespace

import pytest

from routers import query


QUESTION = "Where did I leave my charger?"
IMAGE_URL = "https://example.supabase.co/storage/v1/object/public/photos/charger.jpg"

CHARGER_ROW = {
    "id": 1,
    "description": "A black phone charger on the desk, left of the keyboard.",
    "captured_at": "2026-09-26T14:00:00+00:00",
    "beacons": {"room_name": "Bedroom"},
}
KEYS_ROW = {
    "id": 2,
    "description": "Keys on a kitchen counter.",
    "captured_at": "2026-09-25T09:00:00+00:00",
    "beacons": None,
}

CHARGER_ANSWER = "Your charger is in the Bedroom, based on a photo from September 26, 2026."


def claude_response(stop_reason, content):
    """A stand-in for Claude's response, with just the fields query.py reads."""
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def match_response(matched_photo_id, answer, reasoning="test reasoning"):
    """A response where Claude called record_photo_match with these values."""
    tool_input = {"matched_photo_id": matched_photo_id, "answer": answer, "reasoning": reasoning}
    tool_block = SimpleNamespace(type="tool_use", name="record_photo_match", input=tool_input)
    return claude_response("tool_use", [tool_block])


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


@pytest.fixture
def matched_photo_lookup(fake_supabase):
    """The fake lookup of the matched photo's full row. Returns the charger photo by default."""
    lookup = fake_supabase.tables["photos"].select.return_value.eq.return_value.limit.return_value
    lookup.execute.return_value.data = [{**CHARGER_ROW, "image_url": IMAGE_URL}]
    return lookup


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
# These call get_candidate_photos() directly, since the endpoint no longer
# returns the candidate list itself.


def test_no_complete_photos_gives_empty_candidate_list(candidate_rows):
    candidate_rows([])

    assert query.get_candidate_photos() == []


def test_only_complete_photos_are_requested(fake_supabase, candidate_rows):
    candidate_rows([])

    query.get_candidate_photos()

    photos_table = fake_supabase.tables["photos"]
    photos_table.select.return_value.eq.assert_called_once_with("tagging_status", "complete")


def test_photo_with_beacon_gets_its_room_name(candidate_rows):
    candidate_rows([CHARGER_ROW])

    assert query.get_candidate_photos() == [
        {
            "id": 1,
            "description": "A black phone charger on the desk, left of the keyboard.",
            "room_name": "Bedroom",
            "captured_at": "2026-09-26T14:00:00+00:00",
        },
    ]


def test_photo_without_beacon_gets_location_unknown(candidate_rows):
    candidate_rows([KEYS_ROW])

    assert query.get_candidate_photos()[0]["room_name"] == "Location unknown"


def test_candidates_are_most_recent_first(fake_supabase, candidate_rows):
    # The sorting itself happens in the database, so check that the query
    # asks for newest first and that the order is kept.
    candidate_rows([
        {"id": 3, "description": "newest", "captured_at": "2026-09-28T09:00:00+00:00", "beacons": None},
        {"id": 1, "description": "middle", "captured_at": "2026-09-27T09:00:00+00:00", "beacons": None},
        {"id": 2, "description": "oldest", "captured_at": "2026-09-26T09:00:00+00:00", "beacons": None},
    ])

    candidates = query.get_candidate_photos()

    photos_filter = fake_supabase.tables["photos"].select.return_value.eq.return_value
    photos_filter.order.assert_called_once_with("captured_at", desc=True)

    ids = [candidate["id"] for candidate in candidates]
    assert ids == [3, 1, 2]


def test_candidate_lookup_failure_returns_500(client, fake_supabase):
    photos_query = fake_supabase.tables["photos"].select.return_value.eq.return_value.order.return_value
    photos_query.execute.side_effect = Exception("database down")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not load photos"


# --- Phase 3: Claude matching ---


def test_matching_question_returns_matched_photo(
    client, fake_supabase, fake_claude, candidate_rows, matched_photo_lookup
):
    candidate_rows([CHARGER_ROW, KEYS_ROW])
    fake_claude.messages.create.return_value = match_response(1, CHARGER_ANSWER)

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {
        "matched": True,
        "answer": CHARGER_ANSWER,
        "image_url": IMAGE_URL,
        "description": "A black phone charger on the desk, left of the keyboard.",
        "room_name": "Bedroom",
        "captured_at": "2026-09-26T14:00:00+00:00",
    }

    # The candidate query and the matched-photo lookup share the same fake
    # .select().eq(), so the lookup is the most recent .eq() call.
    photos_select = fake_supabase.tables["photos"].select.return_value
    photos_select.eq.assert_called_with("id", 1)


def test_question_and_candidates_are_sent_to_claude(
    client, fake_claude, candidate_rows, matched_photo_lookup
):
    candidate_rows([CHARGER_ROW, KEYS_ROW])
    fake_claude.messages.create.return_value = match_response(1, CHARGER_ANSWER)

    client.post("/query", json={"question": QUESTION})

    request = fake_claude.messages.create.call_args.kwargs
    assert request["tool_choice"] == {"type": "tool", "name": "record_photo_match"}

    user_message = request["messages"][0]["content"]
    assert QUESTION in user_message
    assert '"room_name": "Bedroom"' in user_message
    assert '"room_name": "Location unknown"' in user_message


def test_no_good_match_returns_matched_false(client, fake_claude, candidate_rows):
    candidate_rows([KEYS_ROW])
    fake_claude.messages.create.return_value = match_response(None, None)

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {"matched": False, "message": "no matching photo found"}


def test_empty_candidate_list_skips_claude(client, fake_claude, candidate_rows):
    candidate_rows([])

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {"matched": False, "message": "no matching photo found"}
    fake_claude.messages.create.assert_not_called()


def test_failed_claude_call_returns_502(client, fake_claude, candidate_rows):
    candidate_rows([CHARGER_ROW])
    fake_claude.messages.create.side_effect = Exception("API down")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not match question to a photo"


@pytest.mark.parametrize(
    "claude_reply",
    [
        # Claude stopped without calling the tool.
        claude_response("max_tokens", []),
        # Claude named a photo that wasn't one of the candidates.
        match_response(99, "Your charger is in the Garage."),
        # Claude picked a photo but gave no answer.
        match_response(1, None),
    ],
    ids=["no_tool_call", "unknown_photo_id", "match_without_answer"],
)
def test_unusable_claude_reply_returns_502(client, fake_claude, candidate_rows, claude_reply):
    candidate_rows([CHARGER_ROW])
    fake_claude.messages.create.return_value = claude_reply

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not match question to a photo"


# --- Phase 4: matched photo lookup ---


def test_matched_photo_lookup_failure_returns_500(
    client, fake_claude, candidate_rows, matched_photo_lookup
):
    candidate_rows([CHARGER_ROW])
    fake_claude.messages.create.return_value = match_response(1, CHARGER_ANSWER)
    matched_photo_lookup.execute.side_effect = Exception("database down")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not load matched photo"
