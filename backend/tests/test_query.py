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


UNSURE_ANSWER = (
    "There's a charger in the Bedroom, based on a photo from September 26, 2026, "
    "but the photo doesn't say whether it's a USB-C charger."
)

UNCLEAR_CANDIDATE = {
    "image_url": IMAGE_URL,
    "room_name": "Bedroom",
    "captured_at": "2026-09-26T14:00:00+00:00",
}


def match_response(matched_photo_id, answer, confidence, reasoning="test reasoning"):
    """A response where Claude called record_photo_match with these values."""
    tool_input = {
        "matched_photo_id": matched_photo_id,
        "answer": answer,
        "confidence": confidence,
        "reasoning": reasoning,
    }
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
    fake_claude.messages.create.return_value = match_response(1, CHARGER_ANSWER, "confident")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {
        "matched": True,
        "confidence": "confident",
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
    fake_claude.messages.create.return_value = match_response(1, CHARGER_ANSWER, "confident")

    client.post("/query", json={"question": QUESTION})

    request = fake_claude.messages.create.call_args.kwargs
    assert request["tool_choice"] == {"type": "tool", "name": "record_photo_match"}

    user_message = request["messages"][0]["content"]
    assert QUESTION in user_message
    assert '"room_name": "Bedroom"' in user_message
    assert '"room_name": "Location unknown"' in user_message


def test_no_good_match_returns_matched_false(client, fake_claude, candidate_rows):
    candidate_rows([KEYS_ROW])
    fake_claude.messages.create.return_value = match_response(None, None, "none")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {"matched": False, "confidence": "none", "message": "no matching photo found"}


def test_tool_schema_requires_confidence():
    schema = query.MATCH_TOOL["input_schema"]

    assert query.MATCH_TOOL["strict"] is True
    assert "confidence" in schema["required"]
    assert schema["properties"]["confidence"]["enum"] == ["confident", "unsure", "none"]

    # Claude fills fields in order, so it must reason and pick a confidence
    # level before it names a photo.
    assert list(schema["properties"]) == ["reasoning", "confidence", "matched_photo_id", "answer"]


def test_unsure_match_returns_unclear_response_with_candidate(
    client, fake_claude, candidate_rows, matched_photo_lookup
):
    candidate_rows([CHARGER_ROW, KEYS_ROW])
    fake_claude.messages.create.return_value = match_response(1, UNSURE_ANSWER, "unsure")

    response = client.post("/query", json={"question": "Where's my USB-C charger?"})

    assert response.status_code == 200
    assert response.json() == {
        "matched": False,
        "confidence": "unsure",
        "unclear": True,
        "message": UNSURE_ANSWER,
        "candidate": UNCLEAR_CANDIDATE,
    }


@pytest.mark.parametrize(
    "claude_reply, expected",
    [
        # Confident, but no answer: a confident match needs an answer, so it
        # becomes unsure, with the fallback message.
        (
            match_response(1, None, "confident"),
            {"matched": False, "confidence": "unsure", "unclear": True, "message": query.UNCLEAR_FALLBACK_MESSAGE, "candidate": UNCLEAR_CANDIDATE},
        ),
        # Same, with an answer that's only whitespace.
        (
            match_response(1, "   ", "confident"),
            {"matched": False, "confidence": "unsure", "unclear": True, "message": query.UNCLEAR_FALLBACK_MESSAGE, "candidate": UNCLEAR_CANDIDATE},
        ),
        # Unsure with no answer keeps the unclear shape but uses the fallback.
        (
            match_response(1, None, "unsure"),
            {"matched": False, "confidence": "unsure", "unclear": True, "message": query.UNCLEAR_FALLBACK_MESSAGE, "candidate": UNCLEAR_CANDIDATE},
        ),
        # Confident or unsure, but no photo named: nothing to show, so no match.
        (match_response(None, CHARGER_ANSWER, "confident"), query.NO_MATCH_RESPONSE),
        (match_response(None, UNSURE_ANSWER, "unsure"), query.NO_MATCH_RESPONSE),
        # None, but a photo named anyway: Claude said nothing is relevant, so no match.
        (match_response(1, CHARGER_ANSWER, "none"), query.NO_MATCH_RESPONSE),
    ],
    ids=[
        "confident_no_answer",
        "confident_blank_answer",
        "unsure_no_answer",
        "confident_no_photo",
        "unsure_no_photo",
        "none_with_photo",
    ],
)
def test_inconsistent_reply_is_downgraded(
    client, fake_claude, candidate_rows, matched_photo_lookup, caplog, claude_reply, expected
):
    candidate_rows([CHARGER_ROW])
    fake_claude.messages.create.return_value = claude_reply

    with caplog.at_level("WARNING", logger="routers.query"):
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == expected

    # Each downgrade logs a warning that names the photo id Claude gave.
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) >= 1
    photo_id = claude_reply.content[0].input["matched_photo_id"]
    if photo_id is not None:
        assert str(photo_id) in warnings[0].getMessage()


def test_empty_candidate_list_skips_claude(client, fake_claude, candidate_rows):
    candidate_rows([])

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {"matched": False, "confidence": "none", "message": "no matching photo found"}
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
        match_response(99, "Your charger is in the Garage.", "confident"),
        match_response(99, "There may be a charger in the Garage.", "unsure"),
    ],
    ids=["no_tool_call", "unknown_photo_id_confident", "unknown_photo_id_unsure"],
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
    fake_claude.messages.create.return_value = match_response(1, CHARGER_ANSWER, "confident")
    matched_photo_lookup.execute.side_effect = Exception("database down")

    response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not load matched photo"
