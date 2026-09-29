import asyncio
import logging

import httpx

from database import supabase


logger = logging.getLogger(__name__)

# How long to wait for the image download before giving up.
DOWNLOAD_TIMEOUT_SECONDS = 30


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


async def trigger_tagging(photo_id: int) -> None:
    """Fetch the photo, download its image and detect its type.

    The Claude call itself (SCRUM-34) isn't written yet, so for now this
    only logs the detected type. It runs as a background task after
    POST /photos has already responded, so failures are logged rather
    than raised. Every failure path tries to set tagging_status to
    'failed'; if the row no longer exists, that update matches nothing
    and does nothing.
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

    logger.info(
        "Photo %s is %s (%d bytes). Claude tagging would happen here (SCRUM-34, not implemented yet)",
        photo_id,
        image_type,
        len(image_bytes),
    )
