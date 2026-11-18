from datetime import datetime, timedelta, timezone

import pytest

from routers import photos


PHOTO_ID = 7


def minutes_ago(minutes: int) -> str:
    """A timestamp from `minutes` ago, in the format Supabase returns."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def status_row(tagging_status, created_at, tagging_started_at=None):
    """A photos row as Supabase returns it for the retag lookup."""
    return {
        "id": PHOTO_ID,
        "created_at": created_at,
        "tagging_status": tagging_status,
        "tagging_started_at": tagging_started_at,
    }


@pytest.fixture
def photo_lookup(fake_supabase):
    """The fake for the lookup: select -> eq(id) -> eq(user_id) -> limit."""
    return fake_supabase.tables["photos"].select.return_value.eq.return_value.eq.return_value.limit.return_value


def claim_filters(fake_supabase):
    """The fake update after its first three filters: update -> eq(id) -> eq(user_id) -> eq(status).

    The last filter depends on the tagging_started_at that was read:
    .eq("tagging_started_at", value), or .is_("tagging_started_at", "null").
    """
    return fake_supabase.tables["photos"].update.return_value.eq.return_value.eq.return_value.eq.return_value


@pytest.fixture
def claim_update(fake_supabase):
    """Make the conditional update match one row, the way a successful claim does.

    Set up for both endings, since which one runs depends on the row read.
    """
    filters = claim_filters(fake_supabase)
    matched = [{"id": PHOTO_ID, "tagging_status": "pending"}]
    filters.eq.return_value.execute.return_value.data = matched
    filters.is_.return_value.execute.return_value.data = matched
    return filters


@pytest.fixture
def scheduled_tagging(monkeypatch):
    """Replace trigger_tagging so no real tagging runs. Returns the photo ids it was called with."""
    photo_ids = []

    async def fake_trigger_tagging(photo_id):
        photo_ids.append(photo_id)

    monkeypatch.setattr(photos, "trigger_tagging", fake_trigger_tagging)
    return photo_ids


def assert_update_sets_pending_with_new_start(fake_supabase):
    """Check the update sets 'pending' and a tagging_started_at of about now."""
    photos_table = fake_supabase.tables["photos"]
    photos_table.update.assert_called_once()
    values = photos_table.update.call_args.args[0]
    assert values["tagging_status"] == "pending"
    started_at = datetime.fromisoformat(values["tagging_started_at"])
    assert datetime.now(timezone.utc) - started_at < timedelta(minutes=1)


def assert_claim_matches(fake_supabase, tagging_status):
    """Check the update's first three filters: id, user_id and the status that was read."""
    filtered = fake_supabase.tables["photos"].update.return_value
    filtered.eq.assert_called_once_with("id", PHOTO_ID)
    filtered.eq.return_value.eq.assert_called_once_with("user_id", photos.PLACEHOLDER_USER_ID)
    filtered.eq.return_value.eq.return_value.eq.assert_called_once_with("tagging_status", tagging_status)


# --- eligible photos ------------------------------------------------------------


@pytest.mark.usefixtures("scheduled_tagging")
def test_failed_photo_is_claimed_and_set_to_pending(client, fake_supabase, photo_lookup, claim_update):
    started_at = minutes_ago(2)
    photo_lookup.execute.return_value.data = [status_row("failed", minutes_ago(30), started_at)]

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 202
    assert response.json() == {"id": PHOTO_ID, "tagging_status": "pending"}

    assert_update_sets_pending_with_new_start(fake_supabase)
    assert_claim_matches(fake_supabase, "failed")
    # Matched on the exact tagging_started_at that was read.
    claim_update.eq.assert_called_once_with("tagging_started_at", started_at)
    claim_update.is_.assert_not_called()


@pytest.mark.usefixtures("scheduled_tagging")
def test_stale_pending_photo_is_claimed(client, fake_supabase, photo_lookup, claim_update):
    # Tagging started 10 minutes ago and never finished.
    started_at = minutes_ago(10)
    photo_lookup.execute.return_value.data = [status_row("pending", minutes_ago(30), started_at)]

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 202
    assert response.json() == {"id": PHOTO_ID, "tagging_status": "pending"}
    assert_claim_matches(fake_supabase, "pending")
    claim_update.eq.assert_called_once_with("tagging_started_at", started_at)


@pytest.mark.usefixtures("scheduled_tagging")
def test_null_tagging_started_at_falls_back_to_created_at(client, fake_supabase, photo_lookup, claim_update):
    # No tagging_started_at (a row from before the column existed), but
    # created 10 minutes ago, so it counts as stale.
    photo_lookup.execute.return_value.data = [status_row("pending", minutes_ago(10), None)]

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 202
    assert_claim_matches(fake_supabase, "pending")
    # A null value is matched with "is null", since "= null" matches nothing.
    claim_update.is_.assert_called_once_with("tagging_started_at", "null")
    claim_update.eq.assert_not_called()


def test_tagging_is_scheduled_exactly_once(client, photo_lookup, claim_update, scheduled_tagging):
    photo_lookup.execute.return_value.data = [status_row("failed", minutes_ago(1))]

    client.post(f"/photos/{PHOTO_ID}/retag")

    # TestClient runs background tasks before post() returns.
    assert scheduled_tagging == [PHOTO_ID]


# --- not eligible -----------------------------------------------------------------


@pytest.mark.parametrize(
    "row",
    [
        status_row("pending", minutes_ago(1)),
        status_row("complete", minutes_ago(10)),
        # Created long ago, but tagging (re)started a minute ago.
        status_row("pending", minutes_ago(60), minutes_ago(1)),
        # Fresh created_at with no tagging_started_at: falls back to created_at.
        status_row("pending", minutes_ago(1), None),
    ],
    ids=["fresh_pending", "complete", "recent_tagging_start", "null_start_fresh_created_at"],
)
def test_ineligible_photo_returns_409(client, fake_supabase, photo_lookup, scheduled_tagging, row):
    photo_lookup.execute.return_value.data = [row]

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 409
    fake_supabase.tables["photos"].update.assert_not_called()
    assert scheduled_tagging == []


def test_claim_with_changed_tagging_started_at_returns_409(
    client, fake_supabase, photo_lookup, claim_update, scheduled_tagging
):
    # Eligible when read, but another request claimed it first and changed
    # tagging_started_at, so this update's filter matches no row.
    photo_lookup.execute.return_value.data = [status_row("failed", minutes_ago(30), minutes_ago(20))]
    claim_update.eq.return_value.execute.return_value.data = []

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 409
    fake_supabase.tables["photos"].update.assert_called_once()
    assert scheduled_tagging == []


def test_claim_matching_no_row_with_null_start_returns_409(client, photo_lookup, claim_update, scheduled_tagging):
    # Same as above, for a row whose tagging_started_at was null when read.
    photo_lookup.execute.return_value.data = [status_row("failed", minutes_ago(1), None)]
    claim_update.is_.return_value.execute.return_value.data = []

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 409
    assert scheduled_tagging == []


# --- not found and errors -----------------------------------------------------------


def test_unknown_photo_returns_404(client, fake_supabase, photo_lookup, scheduled_tagging):
    photo_lookup.execute.return_value.data = []

    response = client.post("/photos/999/retag")

    assert response.status_code == 404
    fake_supabase.tables["photos"].update.assert_not_called()
    assert scheduled_tagging == []


def test_another_users_photo_returns_404(client, fake_supabase, photo_lookup, scheduled_tagging):
    # The fake doesn't filter rows itself, so another user's photo is
    # excluded by asking the database for this user's rows only: the lookup
    # comes back empty. Check that the id and user_id filters were both sent.
    photo_lookup.execute.return_value.data = []

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 404
    filtered = fake_supabase.tables["photos"].select.return_value
    filtered.eq.assert_called_once_with("id", PHOTO_ID)
    filtered.eq.return_value.eq.assert_called_once_with("user_id", photos.PLACEHOLDER_USER_ID)
    assert scheduled_tagging == []


def test_lookup_selects_tagging_started_at(client, fake_supabase, photo_lookup, scheduled_tagging):
    photo_lookup.execute.return_value.data = []

    client.post(f"/photos/{PHOTO_ID}/retag")

    selected_columns = fake_supabase.tables["photos"].select.call_args.args[0]
    assert "tagging_started_at" in selected_columns


def test_lookup_database_error_returns_500(client, fake_supabase, photo_lookup, scheduled_tagging):
    photo_lookup.execute.side_effect = Exception("database is down")

    response = client.post(f"/photos/{PHOTO_ID}/retag")

    assert response.status_code == 500
    fake_supabase.tables["photos"].update.assert_not_called()
    assert scheduled_tagging == []
