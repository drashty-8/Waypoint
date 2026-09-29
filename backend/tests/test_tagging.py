import asyncio
import logging

import pytest

import tagging


PHOTO_ID = 5
IMAGE_URL = "https://example.supabase.co/storage/v1/object/public/photos/test.jpg"

# Just enough of a JPEG's opening bytes for type detection to recognize it.
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 60


@pytest.fixture
def photo_lookup(fake_supabase):
    """The fake photos lookup that trigger_tagging runs. Returns one row by default."""
    lookup = fake_supabase.tables["photos"].select.return_value.eq.return_value.limit.return_value
    lookup.execute.return_value.data = [{"id": PHOTO_ID, "image_url": IMAGE_URL}]
    return lookup


@pytest.fixture
def downloaded_urls(monkeypatch):
    """Replace download_image so no real HTTP request is made. Returns the URLs it was asked for."""
    urls = []

    async def fake_download_image(image_url):
        urls.append(image_url)
        return JPEG_BYTES

    monkeypatch.setattr(tagging, "download_image", fake_download_image)
    return urls


def test_fetches_row_downloads_image_and_logs_detected_type(
    fake_supabase, photo_lookup, downloaded_urls, fake_claude, caplog
):
    with caplog.at_level(logging.INFO, logger="tagging"):
        asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    fake_supabase.tables["photos"].select.return_value.eq.assert_called_once_with("id", PHOTO_ID)
    assert downloaded_urls == [IMAGE_URL]
    assert "image/jpeg" in caplog.text
    # A photo that worked must not be marked failed.
    fake_supabase.tables["photos"].update.assert_not_called()
    # Tagging is still a stub, so Claude must not be called.
    assert fake_claude.method_calls == []


@pytest.mark.usefixtures("fake_claude")
def test_missing_photo_is_logged_and_skips_download(fake_supabase, photo_lookup, downloaded_urls, caplog):
    photo_lookup.execute.return_value.data = []

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    assert downloaded_urls == []
    assert "may have been deleted after upload" in caplog.text
    # The update is still attempted; with no row it just matches nothing.
    fake_supabase.tables["photos"].update.assert_called_once_with({"tagging_status": "failed"})


@pytest.mark.usefixtures("fake_claude")
def test_lookup_failure_is_logged_and_marked_failed(fake_supabase, photo_lookup, downloaded_urls, caplog):
    photo_lookup.execute.side_effect = Exception("database unreachable")

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    assert downloaded_urls == []
    assert "Could not fetch photo" in caplog.text
    photos_table = fake_supabase.tables["photos"]
    photos_table.update.assert_called_once_with({"tagging_status": "failed"})
    photos_table.update.return_value.eq.assert_called_once_with("id", PHOTO_ID)


@pytest.mark.usefixtures("photo_lookup", "fake_claude")
def test_download_failure_is_logged_not_raised(monkeypatch, caplog):
    async def failing_download_image(image_url):
        raise RuntimeError("storage unreachable")

    monkeypatch.setattr(tagging, "download_image", failing_download_image)

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    assert "Could not download image" in caplog.text


async def failing_download(image_url):
    raise RuntimeError("storage unreachable")


async def download_returning_unknown_bytes(image_url):
    return b"not an image at all" + b"\x00" * 60


@pytest.mark.parametrize(
    "fake_download",
    [failing_download, download_returning_unknown_bytes],
    ids=["download_fails", "unrecognized_type"],
)
@pytest.mark.usefixtures("photo_lookup", "fake_claude")
def test_broken_photo_is_marked_failed(fake_supabase, monkeypatch, fake_download):
    monkeypatch.setattr(tagging, "download_image", fake_download)

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    photos_table = fake_supabase.tables["photos"]
    photos_table.update.assert_called_once_with({"tagging_status": "failed"})
    photos_table.update.return_value.eq.assert_called_once_with("id", PHOTO_ID)
    photos_table.update.return_value.eq.return_value.execute.assert_called_once()
