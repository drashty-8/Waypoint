import asyncio
import base64
import io
from types import SimpleNamespace

import anthropic
import httpx2
import pillow_heif
import pytest
from PIL import Image

import tagging


PHOTO_ID = 5
IMAGE_URL = "https://example.supabase.co/storage/v1/object/public/photos/test.jpg"

# Just enough of a JPEG's opening bytes for type detection to recognize it.
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 60

TAG_RESULT = {
    "description": "A black phone charger on the mousepad, left of the keyboard.",
    "tags": ["phone charger", "keyboard", "mousepad"],
}


def claude_response(stop_reason, content):
    """A stand-in for Claude's response, with just the fields tagging.py reads."""
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def tool_call_response(tool_input):
    """A response where Claude called record_photo_tags with tool_input."""
    tool_block = SimpleNamespace(type="tool_use", name="record_photo_tags", input=tool_input)
    return claude_response("tool_use", [tool_block])


def sent_image_source(fake_claude):
    """Return the image "source" dict from the one request sent to the fake Claude client."""
    request = fake_claude.messages.create.call_args.kwargs
    image_block = request["messages"][0]["content"][0]
    return image_block["source"]


@pytest.fixture
def claude_tags(fake_claude):
    """Make the fake Claude client answer with TAG_RESULT."""
    fake_claude.messages.create.return_value = tool_call_response(TAG_RESULT)
    return fake_claude


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


def test_successful_call_saves_description_tags_and_complete_status(
    fake_supabase, photo_lookup, downloaded_urls, claude_tags
):
    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    fake_supabase.tables["photos"].select.return_value.eq.assert_called_once_with("id", PHOTO_ID)
    assert downloaded_urls == [IMAGE_URL]

    # A JPEG is sent as-is: same bytes, base64-encoded, with its own type.
    source = sent_image_source(claude_tags)
    assert source["type"] == "base64"
    assert source["media_type"] == "image/jpeg"
    assert base64.standard_b64decode(source["data"]) == JPEG_BYTES

    # The only update is the success one; the photo isn't also marked failed.
    photos_table = fake_supabase.tables["photos"]
    photos_table.update.assert_called_once_with({
        "description": TAG_RESULT["description"],
        "tags": TAG_RESULT["tags"],
        "tagging_status": "complete",
    })
    photos_table.update.return_value.eq.assert_called_once_with("id", PHOTO_ID)


@pytest.mark.usefixtures("photo_lookup")
def test_heic_photo_is_converted_to_jpeg_before_sending(fake_supabase, monkeypatch, claude_tags):
    # Build a real HEIC so the actual decode and re-encode run.
    heif_file = pillow_heif.from_pillow(Image.new("RGB", (64, 48), "red"))
    heic_buffer = io.BytesIO()
    heif_file.save(heic_buffer)
    heic_bytes = heic_buffer.getvalue()

    async def download_heic(image_url):
        return heic_bytes

    monkeypatch.setattr(tagging, "download_image", download_heic)

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    source = sent_image_source(claude_tags)
    assert source["media_type"] == "image/jpeg"
    sent_image = Image.open(io.BytesIO(base64.standard_b64decode(source["data"])))
    assert sent_image.format == "JPEG"
    assert sent_image.size == (64, 48)
    fake_supabase.tables["photos"].update.assert_called_once()
    assert fake_supabase.tables["photos"].update.call_args.args[0]["tagging_status"] == "complete"


def raise_connection_error(fake_claude):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_claude.messages.create.side_effect = anthropic.APIConnectionError(request=request)


def return_refusal(fake_claude):
    fake_claude.messages.create.return_value = claude_response("refusal", [])


def return_text_instead_of_tool_call(fake_claude):
    text_block = SimpleNamespace(type="text", text="I can't describe this photo.")
    fake_claude.messages.create.return_value = claude_response("end_turn", [text_block])


@pytest.mark.parametrize(
    "set_up_claude",
    [raise_connection_error, return_refusal, return_text_instead_of_tool_call],
    ids=["network_error", "refusal", "no_tool_call"],
)
@pytest.mark.usefixtures("photo_lookup", "downloaded_urls")
def test_failed_claude_call_is_marked_failed(fake_supabase, fake_claude, set_up_claude):
    set_up_claude(fake_claude)

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    fake_claude.messages.create.assert_called_once()
    photos_table = fake_supabase.tables["photos"]
    photos_table.update.assert_called_once_with({"tagging_status": "failed"})
    photos_table.update.return_value.eq.assert_called_once_with("id", PHOTO_ID)


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


@pytest.mark.usefixtures("photo_lookup", "downloaded_urls")
def test_image_over_claude_size_limit_is_marked_failed_without_sending(
    fake_supabase, fake_claude, monkeypatch, caplog
):
    # Set the limit to one byte below the test image's base64 size, rather
    # than building a real 10MB image.
    encoded_size = len(base64.standard_b64encode(JPEG_BYTES))
    monkeypatch.setattr(tagging, "MAX_CLAUDE_IMAGE_BASE64_BYTES", encoded_size - 1)

    asyncio.run(tagging.trigger_tagging(PHOTO_ID))

    fake_claude.messages.create.assert_not_called()
    assert "exceeds Claude's 10MB limit" in caplog.text
    fake_supabase.tables["photos"].update.assert_called_once_with({"tagging_status": "failed"})
