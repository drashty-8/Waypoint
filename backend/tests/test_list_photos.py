from datetime import datetime, timedelta, timezone

import pytest

from routers import photos


IMAGE_URL = "https://example.supabase.co/storage/v1/object/public/photos/test.jpg"


def minutes_ago(minutes: int) -> str:
    """A created_at value from `minutes` ago, in the format Supabase returns."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def photo_row(photo_id, tagging_status, created_at, room_name="Bedroom", tagging_started_at=None):
    """A photos row as Supabase returns it when selected with LIST_COLUMNS.

    tagging_started_at defaults to None, so staleness falls back to created_at.
    """
    beacons = None
    if room_name is not None:
        beacons = {"room_name": room_name}

    return {
        "id": photo_id,
        "created_at": created_at,
        "tagging_status": tagging_status,
        "tagging_started_at": tagging_started_at,
        "image_url": IMAGE_URL,
        "beacons": beacons,
    }


@pytest.fixture
def retag_query(fake_supabase):
    """The fake for the needs_retag=true query: select -> eq(user_id) -> in_(status)."""
    return fake_supabase.tables["photos"].select.return_value.eq.return_value.in_.return_value


@pytest.fixture
def recent_query(fake_supabase):
    """The fake for the plain list query: select -> eq(user_id) -> order -> limit."""
    return fake_supabase.tables["photos"].select.return_value.eq.return_value.order.return_value.limit.return_value


def returned_ids(response):
    return [item["id"] for item in response.json()]


# --- needs_retag=true ---------------------------------------------------------


def test_failed_photo_is_included(client, retag_query):
    retag_query.execute.return_value.data = [photo_row(1, "failed", minutes_ago(1))]

    response = client.get("/photos", params={"needs_retag": "true"})

    assert response.status_code == 200
    assert returned_ids(response) == [1]


def test_lookup_selects_tagging_started_at(client, fake_supabase, retag_query):
    retag_query.execute.return_value.data = []

    client.get("/photos", params={"needs_retag": "true"})

    selected_columns = fake_supabase.tables["photos"].select.call_args.args[0]
    assert "tagging_started_at" in selected_columns


def test_stale_pending_photo_is_included(client, retag_query):
    # tagging_started_at is null here, so staleness falls back to created_at.
    retag_query.execute.return_value.data = [photo_row(1, "pending", minutes_ago(10))]

    response = client.get("/photos", params={"needs_retag": "true"})

    assert returned_ids(response) == [1]


def test_fresh_pending_photo_is_excluded(client, retag_query):
    retag_query.execute.return_value.data = [photo_row(1, "pending", minutes_ago(1))]

    response = client.get("/photos", params={"needs_retag": "true"})

    assert response.status_code == 200
    assert response.json() == []


def test_pending_photo_with_recent_tagging_start_is_excluded(client, retag_query):
    # Created long ago, but tagging (re)started a minute ago, so it isn't stuck.
    retag_query.execute.return_value.data = [
        photo_row(1, "pending", minutes_ago(60), tagging_started_at=minutes_ago(1))
    ]

    response = client.get("/photos", params={"needs_retag": "true"})

    assert response.status_code == 200
    assert response.json() == []


def test_pending_photo_with_old_tagging_start_is_included(client, retag_query):
    retag_query.execute.return_value.data = [
        photo_row(1, "pending", minutes_ago(60), tagging_started_at=minutes_ago(10))
    ]

    response = client.get("/photos", params={"needs_retag": "true"})

    assert returned_ids(response) == [1]


def test_complete_photo_is_excluded(client, retag_query):
    # The database query already leaves out 'complete' rows. This checks the
    # Python filter also drops one if it ever got through.
    retag_query.execute.return_value.data = [photo_row(1, "complete", minutes_ago(10))]

    response = client.get("/photos", params={"needs_retag": "true"})

    assert response.json() == []


def test_retag_query_filters_to_the_current_user_and_retag_statuses(client, fake_supabase, retag_query):
    # The fake doesn't filter rows itself, so another user's failed photo is
    # excluded by asking the database for this user's rows only. Check that
    # the user_id filter and the status filter were both sent.
    retag_query.execute.return_value.data = []

    client.get("/photos", params={"needs_retag": "true"})

    photos_table = fake_supabase.tables["photos"]
    photos_table.select.return_value.eq.assert_called_once_with("user_id", photos.PLACEHOLDER_USER_ID)
    photos_table.select.return_value.eq.return_value.in_.assert_called_once_with(
        "tagging_status", ["failed", "pending"]
    )


def test_retag_results_are_newest_first_and_limited(client, retag_query):
    retag_query.execute.return_value.data = [
        photo_row(1, "failed", minutes_ago(30)),
        photo_row(2, "failed", minutes_ago(10)),
        photo_row(3, "pending", minutes_ago(20)),
    ]

    response = client.get("/photos", params={"needs_retag": "true", "limit": 2})

    assert returned_ids(response) == [2, 3]


def test_room_name_is_null_when_photo_has_no_beacon(client, retag_query):
    retag_query.execute.return_value.data = [
        photo_row(1, "failed", minutes_ago(1), room_name=None),
        photo_row(2, "failed", minutes_ago(2), room_name="Kitchen"),
    ]

    response = client.get("/photos", params={"needs_retag": "true"})

    items = response.json()
    assert items[0]["room_name"] is None
    assert items[1]["room_name"] == "Kitchen"
    assert set(items[0]) == {"id", "created_at", "tagging_status", "image_url", "room_name"}


# --- plain list -----------------------------------------------------------------


def test_plain_list_is_the_users_photos_newest_first_with_default_limit(client, fake_supabase, recent_query):
    recent_query.execute.return_value.data = [photo_row(1, "complete", minutes_ago(1))]

    response = client.get("/photos")

    assert response.status_code == 200
    assert returned_ids(response) == [1]
    filtered = fake_supabase.tables["photos"].select.return_value
    filtered.eq.assert_called_once_with("user_id", photos.PLACEHOLDER_USER_ID)
    filtered.eq.return_value.order.assert_called_once_with("created_at", desc=True)
    filtered.eq.return_value.order.return_value.limit.assert_called_once_with(50)


@pytest.mark.usefixtures("fake_supabase")
def test_limit_over_200_is_rejected(client):
    response = client.get("/photos", params={"limit": 201})

    assert response.status_code == 422


def test_lookup_failure_returns_500(client, recent_query):
    recent_query.execute.side_effect = Exception("database is down")

    response = client.get("/photos")

    assert response.status_code == 500
