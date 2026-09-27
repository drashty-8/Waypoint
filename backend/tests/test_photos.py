from unittest.mock import MagicMock

import pytest

from routers import photos


CAPTURED_AT = "2026-09-26T14:00:00Z"
BEACON_UUID = "11111111-2222-3333-4444-555555555555"
IMAGE_URL = "https://example.supabase.co/storage/v1/object/public/photos/test.jpg"
NEW_PHOTO_ID = 42

# Just enough of each format's opening bytes (its "signature") for type
# detection to recognize it. These aren't full, viewable images.
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 60
GIF_BYTES = b"GIF89a" + b"\x00" * 60
EXE_BYTES = b"MZ\x90\x00" + b"\x00" * 60


def heif_family_bytes(major_brand: bytes, compatible_brands: bytes) -> bytes:
    """Build the opening "ftyp" box shared by HEIC, HEIF and AVIF files."""
    box_body = b"ftyp" + major_brand + b"\x00\x00\x00\x00" + compatible_brands
    box_size = (4 + len(box_body)).to_bytes(4, "big")
    return box_size + box_body + b"\x00" * 60


@pytest.fixture
def photos_supabase(fake_supabase):
    """A fake Supabase where every step of POST /photos succeeds.

    Every test in this file needs it. Tests that need a step to fail
    override just that part.
    """
    beacon_lookup = fake_supabase.tables["beacons"].select.return_value.eq.return_value.limit.return_value
    beacon_lookup.execute.return_value.data = [{"id": 1}]

    photo_insert = fake_supabase.tables["photos"].insert.return_value
    photo_insert.execute.return_value.data = [{"id": NEW_PHOTO_ID, "tagging_status": "pending"}]

    fake_supabase.buckets["photos"].get_public_url.return_value = IMAGE_URL

    return fake_supabase


@pytest.fixture
def tagging_calls(monkeypatch):
    """Replace trigger_tagging with a recorder and return the photo ids it was called with.

    Every test in this file needs it, so tagging never runs for real.
    """
    calls = []
    monkeypatch.setattr(photos, "trigger_tagging", lambda photo_id: calls.append(photo_id))
    return calls


def post_photo(client, image=("photo.jpg", JPEG_BYTES, "image/jpeg"), captured_at=CAPTURED_AT, beacon_uuid=None):
    """Send POST /photos, leaving out any field passed as None."""
    files = {}
    if image is not None:
        files["image"] = image

    data = {}
    if captured_at is not None:
        data["captured_at"] = captured_at
    if beacon_uuid is not None:
        data["beacon_uuid"] = beacon_uuid

    return client.post("/photos", files=files, data=data)


def uploaded_content_type_and_path(fake_supabase):
    """Return the Content-Type and Storage path from the upload call."""
    upload_args = fake_supabase.buckets["photos"].upload.call_args.args
    path = upload_args[0]
    options = upload_args[2]
    return options["content-type"], path


# --- Successful uploads ---

def test_upload_with_beacon_returns_201_inserts_row_and_starts_tagging(client, photos_supabase, tagging_calls):
    response = post_photo(client, beacon_uuid=BEACON_UUID)

    assert response.status_code == 201
    assert response.json() == {"id": NEW_PHOTO_ID, "tagging_status": "pending"}

    inserted_row = photos_supabase.tables["photos"].insert.call_args.args[0]
    assert inserted_row == {
        "user_id": photos.PLACEHOLDER_USER_ID,
        "captured_at": "2026-09-26T14:00:00+00:00",
        "image_url": IMAGE_URL,
        "beacon_uuid": BEACON_UUID,
    }
    assert tagging_calls == [NEW_PHOTO_ID]


@pytest.mark.usefixtures("tagging_calls")
def test_upload_without_beacon_returns_201_and_skips_beacon_lookup(client, photos_supabase):
    response = post_photo(client)

    assert response.status_code == 201
    tables_used = [call.args[0] for call in photos_supabase.client.table.call_args_list]
    assert "beacons" not in tables_used
    inserted_row = photos_supabase.tables["photos"].insert.call_args.args[0]
    assert inserted_row["beacon_uuid"] is None


@pytest.mark.usefixtures("tagging_calls")
def test_blank_beacon_uuid_is_treated_as_not_sent(client, photos_supabase):
    response = post_photo(client, beacon_uuid="")

    assert response.status_code == 201
    tables_used = [call.args[0] for call in photos_supabase.client.table.call_args_list]
    assert "beacons" not in tables_used
    inserted_row = photos_supabase.tables["photos"].insert.call_args.args[0]
    assert inserted_row["beacon_uuid"] is None


# --- Phase 1: request validation (400) ---

@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_missing_image_returns_400(client):
    response = post_photo(client, image=None)

    assert response.status_code == 400
    assert response.json()["detail"] == "image is required"


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_empty_image_returns_400(client):
    response = post_photo(client, image=("photo.jpg", b"", "image/jpeg"))

    assert response.status_code == 400
    assert response.json()["detail"] == "image is empty"


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_gif_image_returns_400(client):
    response = post_photo(client, image=("photo.gif", GIF_BYTES, "image/gif"))

    assert response.status_code == 400
    assert response.json()["detail"].startswith("image must be one of")


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_image_over_10mb_returns_400(client):
    too_big = JPEG_BYTES + b"\x00" * photos.MAX_IMAGE_BYTES

    response = post_photo(client, image=("photo.jpg", too_big, "image/jpeg"))

    assert response.status_code == 400
    assert response.json()["detail"] == "image must be 10MB or smaller"


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_missing_captured_at_returns_400(client):
    response = post_photo(client, captured_at=None)

    assert response.status_code == 400
    assert response.json()["detail"] == "captured_at is required"


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_unparseable_captured_at_returns_400(client):
    response = post_photo(client, captured_at="yesterday")

    assert response.status_code == 400
    assert response.json()["detail"].startswith("captured_at must be an ISO 8601 timestamp")


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_captured_at_without_timezone_returns_400(client):
    response = post_photo(client, captured_at="2026-09-26T14:00:00")

    assert response.status_code == 400
    assert response.json()["detail"].startswith("captured_at must include a timezone")


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_invalid_beacon_uuid_returns_400(client):
    response = post_photo(client, beacon_uuid="not-a-uuid")

    assert response.status_code == 400
    assert response.json()["detail"] == "beacon_uuid must be a valid UUID"


# --- Phase 1: file type detection from the file's own bytes ---

@pytest.mark.usefixtures("tagging_calls")
def test_png_is_accepted_and_stored_as_png(client, photos_supabase):
    response = post_photo(client, image=("photo.png", PNG_BYTES, "image/png"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/png"
    assert path.endswith(".png")


@pytest.mark.usefixtures("tagging_calls")
def test_webp_is_accepted_and_stored_as_webp(client, photos_supabase):
    response = post_photo(client, image=("photo.webp", WEBP_BYTES, "image/webp"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/webp"
    assert path.endswith(".webp")


@pytest.mark.usefixtures("tagging_calls")
def test_heic_brand_heic_is_accepted_and_stored_as_heic(client, photos_supabase):
    image_bytes = heif_family_bytes(b"heic", b"mif1heic")

    response = post_photo(client, image=("photo.heic", image_bytes, "image/heic"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/heic"
    assert path.endswith(".heic")


@pytest.mark.usefixtures("tagging_calls")
def test_heif_brand_mif1_is_accepted_and_stored_as_heif(client, photos_supabase):
    image_bytes = heif_family_bytes(b"mif1", b"mif1")

    response = post_photo(client, image=("photo.heif", image_bytes, "image/heif"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/heif"
    assert path.endswith(".heif")


@pytest.mark.usefixtures("tagging_calls")
def test_heic_brand_heix_is_accepted_and_stored_as_heif(client, photos_supabase):
    # heix is a HEIC variant, but it's labelled image/heif on purpose
    # (see docs/decisions.md).
    image_bytes = heif_family_bytes(b"heix", b"mif1heix")

    response = post_photo(client, image=("photo.heic", image_bytes, "image/heic"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/heif"
    assert path.endswith(".heif")


@pytest.mark.usefixtures("photos_supabase", "tagging_calls")
def test_avif_image_returns_400(client):
    image_bytes = heif_family_bytes(b"avif", b"mif1avif")

    response = post_photo(client, image=("photo.avif", image_bytes, "image/avif"))

    assert response.status_code == 400


@pytest.mark.usefixtures("tagging_calls")
def test_exe_labelled_as_jpeg_returns_400(client, photos_supabase):
    response = post_photo(client, image=("photo.jpg", EXE_BYTES, "image/jpeg"))

    assert response.status_code == 400
    photos_supabase.buckets["photos"].upload.assert_not_called()


@pytest.mark.usefixtures("tagging_calls")
def test_text_labelled_as_png_returns_400(client, photos_supabase):
    response = post_photo(client, image=("photo.png", b"hello, not an image", "image/png"))

    assert response.status_code == 400
    photos_supabase.buckets["photos"].upload.assert_not_called()


@pytest.mark.usefixtures("tagging_calls")
def test_jpeg_labelled_as_octet_stream_is_stored_as_jpeg(client, photos_supabase):
    response = post_photo(client, image=("photo", JPEG_BYTES, "application/octet-stream"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/jpeg"
    assert path.endswith(".jpg")


@pytest.mark.usefixtures("tagging_calls")
def test_jpeg_labelled_as_png_is_stored_as_jpeg(client, photos_supabase):
    response = post_photo(client, image=("photo.png", JPEG_BYTES, "image/png"))

    assert response.status_code == 201
    content_type, path = uploaded_content_type_and_path(photos_supabase)
    assert content_type == "image/jpeg"
    assert path.endswith(".jpg")


# --- Phase 2: beacon existence check (404, or 500 if the lookup fails) ---

@pytest.mark.usefixtures("tagging_calls")
def test_unknown_beacon_returns_404_without_uploading(client, photos_supabase):
    beacon_lookup = photos_supabase.tables["beacons"].select.return_value.eq.return_value.limit.return_value
    beacon_lookup.execute.return_value.data = []

    response = post_photo(client, beacon_uuid=BEACON_UUID)

    assert response.status_code == 404
    assert response.json()["detail"] == "beacon_uuid not found"
    photos_supabase.buckets["photos"].upload.assert_not_called()


@pytest.mark.usefixtures("tagging_calls")
def test_beacon_lookup_failure_returns_500_without_uploading(client, photos_supabase):
    beacon_lookup = photos_supabase.tables["beacons"].select.return_value.eq.return_value.limit.return_value
    beacon_lookup.execute.side_effect = Exception("database is down")

    response = post_photo(client, beacon_uuid=BEACON_UUID)

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not check beacon_uuid"
    photos_supabase.buckets["photos"].upload.assert_not_called()


# --- Phase 3: Storage upload (502) ---

@pytest.mark.usefixtures("tagging_calls")
def test_storage_upload_failure_returns_502_without_inserting(client, photos_supabase):
    photos_supabase.buckets["photos"].upload.side_effect = Exception("Storage is down")

    response = post_photo(client)

    assert response.status_code == 502
    photos_supabase.tables["photos"].insert.assert_not_called()


# --- Phase 4: database insert with one retry (500) ---

def test_insert_that_fails_once_is_retried_and_returns_201(client, photos_supabase, tagging_calls):
    retry_row = MagicMock(data=[{"id": 7, "tagging_status": "pending"}])
    photo_insert = photos_supabase.tables["photos"].insert.return_value
    photo_insert.execute.side_effect = [Exception("brief database error"), retry_row]

    response = post_photo(client)

    assert response.status_code == 201
    assert response.json()["id"] == 7
    photos_supabase.buckets["photos"].remove.assert_not_called()
    assert tagging_calls == [7]


def test_insert_that_fails_twice_deletes_upload_and_returns_500(client, photos_supabase, tagging_calls):
    photo_insert = photos_supabase.tables["photos"].insert.return_value
    photo_insert.execute.side_effect = Exception("database is down")

    response = post_photo(client)

    assert response.status_code == 500
    assert photo_insert.execute.call_count == 2

    uploaded_path = photos_supabase.buckets["photos"].upload.call_args.args[0]
    photos_supabase.buckets["photos"].remove.assert_called_once_with([uploaded_path])
    assert tagging_calls == []
