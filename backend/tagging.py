import asyncio
import base64
import io
import logging

import httpx
import pillow_heif

from claude_client import client
from database import supabase


logger = logging.getLogger(__name__)

# How long to wait for the image download before giving up.
DOWNLOAD_TIMEOUT_SECONDS = 30

TAGGING_MODEL = "claude-haiku-4-5-20251001"
# A tagging answer is a few hundred tokens. This is only a ceiling, and
# unused tokens aren't billed, so it's set with plenty of room to spare.
TAGGING_MAX_TOKENS = 4096

# Claude can't read HEIC/HEIF, so those get re-encoded as JPEG first.
HEIF_TYPES = {"image/heic", "image/heif"}
JPEG_QUALITY = 90

# The Claude API's per-image limit is 10MB, measured on the base64-encoded
# data, not the raw file (base64 is about a third bigger). The 5MB figure
# sometimes quoted is for Amazon Bedrock and Google Cloud, not the direct API.
# https://platform.claude.com/docs/en/build-with-claude/vision#request-limits
MAX_CLAUDE_IMAGE_BASE64_BYTES = 10 * 1024 * 1024

TAGGING_PROMPT = (
    "You are analyzing a photo for a personal item-recall app. The user will later "
    "ask natural-language questions like 'where did I leave my charger?' and this "
    "description is the only thing that determines whether the right photo gets found."
    "\n\n"
    "Describe the scene in a short paragraph, not a single sentence. Prioritize "
    "small, portable, easy-to-lose items (keys, chargers, cables, earbuds, personal "
    "items) ahead of furniture and large equipment. Mention furniture and large "
    "equipment only as landmarks, to describe where the small items are — e.g. "
    "'a phone charger on the mousepad, left of the keyboard.'"
    "\n\n"
    "When an object's identity is ambiguous, describe its visible appearance (shape, "
    "color, material) rather than guessing a specific category. Do not state a "
    "confident label you're not sure of."
    "\n\n"
    "Only state text as fact when it's clearly, confidently legible. If text is "
    "blurry, angled, or partially obscured, describe the object without quoting "
    "specific words."
    "\n\n"
    "Treat physical writing and printed surfaces — whiteboards, papers, sticky notes, "
    "book and magazine covers, printed labels — as real objects, including any "
    "legible text on them. Do not describe what's currently displayed on a screen "
    "(a monitor, laptop, or phone showing an app, code, or video) — mention the "
    "screen itself as one object, not its contents, since a screen's display is "
    "transient and not a fact about the room."
)

TAGGING_TOOL = {
    "name": "record_photo_tags",
    "description": (
        "Record a description of the photo and the objects visible in it. "
        "These are used later to answer questions like 'where did I leave my charger?'"
    ),
    # strict makes the API guarantee the tool input matches this schema exactly.
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": (
                    "A short paragraph describing the scene. Prioritize small, portable "
                    "items and give each one's location relative to a landmark, e.g. "
                    "'a phone charger on the mousepad, left of the keyboard'. If an "
                    "object's identity or its text is uncertain, describe how it looks "
                    "(shape, color, material) instead of guessing."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Short lowercase object names, small portable items first, e.g. "
                    "'phone charger', 'keys', 'wallet'. Names only, with no location "
                    "text; locations belong in the description."
                ),
            },
        },
        "required": ["description", "tags"],
        "additionalProperties": False,
    },
}


def fetch_photo_row(photo_id: int) -> dict | None:
    """Return the photos row for photo_id, or None if there isn't one."""
    result = (
        supabase.table("photos")
        .select("id, image_url")
        .eq("id", photo_id)
        .limit(1)
        .execute()
    )

    if len(result.data) == 0:
        return None

    return result.data[0]


def mark_tagging_failed(photo_id: int) -> None:
    """Set the photo's tagging_status to 'failed' so it isn't left looking 'pending'."""
    supabase.table("photos").update({"tagging_status": "failed"}).eq("id", photo_id).execute()


async def record_failure(photo_id: int) -> None:
    """Mark the photo as failed, logging (not raising) if that update itself fails.

    Retrying failed photos later is SCRUM-29; this only records the status.
    """
    try:
        # Synchronous Supabase call, so it runs in a worker thread (see trigger_tagging).
        await asyncio.to_thread(mark_tagging_failed, photo_id)
    except Exception:
        logger.exception("Could not set tagging_status to 'failed' for photo %s", photo_id)


async def download_image(image_url: str) -> bytes:
    """Download the image at image_url. Raises if the request fails or returns an error status."""
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS) as http_client:
        response = await http_client.get(image_url)
        response.raise_for_status()
        return response.content


def prepare_image_for_claude(image_bytes: bytes, image_type: str) -> tuple[bytes, str]:
    """Return image bytes Claude can read, plus their MIME type.

    HEIC/HEIF is decoded and re-encoded as JPEG at the same pixel
    dimensions. Any other type is returned unchanged.
    """
    if image_type not in HEIF_TYPES:
        return image_bytes, image_type

    heif_file = pillow_heif.open_heif(io.BytesIO(image_bytes))
    # JPEG has no alpha channel, so convert to plain RGB.
    image = heif_file.to_pillow().convert("RGB")

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY)
    return output.getvalue(), "image/jpeg"


def request_tags(image_base64: str, media_type: str):
    """Send the base64-encoded image to Claude and return its response."""
    return client.messages.create(
        model=TAGGING_MODEL,
        max_tokens=TAGGING_MAX_TOKENS,
        tools=[TAGGING_TOOL],
        # Make Claude answer by calling the tool, not with plain text.
        tool_choice={"type": "tool", "name": TAGGING_TOOL["name"]},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_base64},
                },
                {"type": "text", "text": TAGGING_PROMPT},
            ],
        }],
    )


def find_tag_result(response) -> dict | None:
    """Return the tool call's input ({"description", "tags"}), or None if Claude didn't make one."""
    # Anything other than "tool_use" (e.g. "max_tokens" or "refusal") means
    # the tool call is missing or incomplete.
    if response.stop_reason != "tool_use":
        return None

    for block in response.content:
        if block.type == "tool_use" and block.name == TAGGING_TOOL["name"]:
            return block.input

    return None


def save_tags(photo_id: int, description: str, tags: list[str]) -> None:
    """Write Claude's description and tags to the photo's row and mark it complete."""
    supabase.table("photos").update({
        "description": description,
        "tags": tags,
        "tagging_status": "complete",
    }).eq("id", photo_id).execute()


async def trigger_tagging(photo_id: int) -> None:
    """Fetch the photo, send it to Claude and save the description and tags.

    It runs as a background task after POST /photos has already
    responded, so failures are logged rather than raised. Every failure
    path tries to set tagging_status to 'failed'; if the row no longer
    exists, that update matches nothing and does nothing. There's no
    retrying here; that's SCRUM-29.
    """
    # Imported here rather than at the top of the file because
    # routers/photos.py imports this module. Importing routers.photos
    # back while both files are still loading would be a circular import.
    from routers.photos import detect_image_type

    # The Supabase client is synchronous, so it runs in a worker thread.
    # Otherwise it would block the event loop while it waits on the network.
    try:
        photo = await asyncio.to_thread(fetch_photo_row, photo_id)
    except Exception:
        logger.exception("Could not fetch photo %s; marking it failed", photo_id)
        await record_failure(photo_id)
        return

    if photo is None:
        logger.error(
            "Photo %s not found; the row may have been deleted after upload. Skipping tagging",
            photo_id,
        )
        await record_failure(photo_id)
        return

    try:
        image_bytes = await download_image(photo["image_url"])
    except Exception:
        logger.exception("Could not download image for photo %s; marking it failed", photo_id)
        await record_failure(photo_id)
        return

    image_type = detect_image_type(image_bytes)
    if image_type is None:
        logger.error("Photo %s has an unrecognized image type; marking it failed", photo_id)
        await record_failure(photo_id)
        return

    # Decoding and re-encoding a HEIC is slow CPU work, so it also runs in a
    # worker thread to keep the event loop free.
    try:
        send_bytes, media_type = await asyncio.to_thread(
            prepare_image_for_claude, image_bytes, image_type
        )
    except Exception:
        logger.exception("Could not convert %s image for photo %s; marking it failed", image_type, photo_id)
        await record_failure(photo_id)
        return

    # Checked after any HEIC conversion, on the base64 text, because that's
    # what the API measures. Failing here gives a clear reason instead of a
    # generic rejection from the API.
    image_base64 = base64.standard_b64encode(send_bytes).decode("utf-8")
    if len(image_base64) > MAX_CLAUDE_IMAGE_BASE64_BYTES:
        logger.error(
            "Photo %s: image exceeds Claude's 10MB limit (%d bytes base64-encoded, max %d); marking it failed",
            photo_id,
            len(image_base64),
            MAX_CLAUDE_IMAGE_BASE64_BYTES,
        )
        await record_failure(photo_id)
        return

    # The shared Claude client is synchronous too, so the same applies.
    try:
        response = await asyncio.to_thread(request_tags, image_base64, media_type)
    except Exception:
        logger.exception("Claude call failed for photo %s; marking it failed", photo_id)
        await record_failure(photo_id)
        return

    tag_result = find_tag_result(response)
    if tag_result is None:
        logger.error(
            "Claude did not return tags for photo %s (stop_reason=%s); marking it failed",
            photo_id,
            response.stop_reason,
        )
        await record_failure(photo_id)
        return

    try:
        await asyncio.to_thread(save_tags, photo_id, tag_result["description"], tag_result["tags"])
    except Exception:
        logger.exception("Could not save tags for photo %s; marking it failed", photo_id)
        await record_failure(photo_id)
        return

    logger.info("Tagged photo %s with %d tags", photo_id, len(tag_result["tags"]))
