import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
import filetype
from pydantic import BaseModel

from database import supabase
from tagging import trigger_tagging


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/photos", tags=["photos"])

# Every row uses this one shared user_id until real auth arrives in COMP491.
PLACEHOLDER_USER_ID = "e45185b1-c22f-4cb7-9d41-a70318ef7cf2"

PHOTOS_BUCKET = "photos"

# Matches the photos bucket's own 10MB file limit.
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Allowed image types, mapped to the file extension used in Storage.
# Same list the photos bucket accepts. The type is detected from the
# file's own bytes, never taken from the client's Content-Type header.
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

# HEIF "brand" codes that filetype doesn't recognize. filetype only
# reports HEIC files branded "heic", so plain HEIF ("mif1", "msf1") and
# HEIC variants like "heix" (10-bit, used by some Android phones) are
# checked here instead.
EXTRA_HEIF_BRANDS = {b"mif1", b"msf1", b"heix", b"heim", b"heis", b"hevc", b"hevx"}

# A beacon's major and minor are each 16-bit numbers, so 0 to 65535.
MAX_BEACON_NUMBER = 65535

# A photo still 'pending' this long after its row was written is assumed
# stuck (e.g. the server restarted mid-tagging), so it counts as needing a retag.
STALE_PENDING_AFTER = timedelta(minutes=5)

# GET /photos page size: used when no limit is sent, and the most allowed.
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200

# Columns GET /photos returns. "beacons(room_name)" follows photos.beacon_id
# to the beacons table (same as routers/query.py), so room_name comes back
# in the same query; for a photo with no beacon, "beacons" is None.
LIST_COLUMNS = "id, created_at, tagging_status, image_url, beacons(room_name)"


class PhotoSummary(BaseModel):
    """One photo in the GET /photos response."""

    id: int
    created_at: datetime
    tagging_status: str
    image_url: str
    # None when the photo was taken without a beacon.
    room_name: str | None


def detect_image_type(image_bytes: bytes) -> str | None:
    """Work out the file's real type from its first bytes (its "signature").

    Returns a MIME type like "image/jpeg", or None if it isn't recognized.
    """
    kind = filetype.guess(image_bytes)
    if kind is not None:
        return kind.mime

    # HEIF files start with a 4-byte size, then "ftyp", then a 4-byte brand.
    if image_bytes[4:8] == b"ftyp" and image_bytes[8:12] in EXTRA_HEIF_BRANDS:
        return "image/heif"

    return None


def parse_captured_at(value: str | None) -> datetime:
    """Parse captured_at, or raise a 400 if it's missing, malformed or has no timezone."""
    if value is None or value.strip() == "":
        raise HTTPException(status_code=400, detail="captured_at is required")

    try:
        captured_at = datetime.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="captured_at must be an ISO 8601 timestamp, e.g. 2026-09-26T14:00:00Z",
        )

    # A timestamp with no offset or Z is ambiguous, so reject it rather than guess.
    if captured_at.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="captured_at must include a timezone, e.g. 2026-09-26T14:00:00Z",
        )

    return captured_at


def is_blank(value: str | None) -> bool:
    """True if a form field wasn't sent or was sent empty, which count the same."""
    return value is None or value.strip() == ""


def parse_beacon_uuid(value: str) -> str:
    """Return beacon_uuid in standard form, or raise a 400 if it's invalid."""
    try:
        return str(uuid.UUID(value.strip()))
    except ValueError:
        raise HTTPException(status_code=400, detail="beacon_uuid must be a valid UUID")


def parse_beacon_number(field_name: str, value: str) -> int:
    """Return a beacon major or minor as an int, or raise a 400 unless it's a whole number from 0 to 65535."""
    text = value.strip()

    # Only plain ASCII digits are allowed. int() on its own would also
    # accept things like "+5", "1_000" or non-ASCII digits like "٣".
    # ([0-9] is used rather than \d, which matches non-ASCII digits too.)
    if not re.fullmatch(r"[0-9]+", text):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be an integer from 0 to {MAX_BEACON_NUMBER}",
        )

    # Leading zeros don't change the value, so drop them ("0005" is 5).
    # If nothing is left, the value was all zeros, i.e. 0.
    digits = text.lstrip("0")
    if digits == "":
        digits = "0"

    # Anything longer than 5 digits is out of range. Checking the length
    # before int() also means int() never sees a very long string: Python
    # refuses to convert more than 4300 digits and raises instead.
    if len(digits) > len(str(MAX_BEACON_NUMBER)):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be an integer from 0 to {MAX_BEACON_NUMBER}",
        )

    number = int(digits)
    if number > MAX_BEACON_NUMBER:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be an integer from 0 to {MAX_BEACON_NUMBER}",
        )

    return number


def parse_beacon(beacon_uuid: str | None, beacon_major: str | None, beacon_minor: str | None) -> dict | None:
    """Validate the beacon triple (uuid, major, minor).

    Returns {"uuid", "major", "minor"}, or None if none of the three was
    sent. Raises a 400 if only some of them were sent or any is invalid.
    """
    fields = {
        "beacon_uuid": beacon_uuid,
        "beacon_major": beacon_major,
        "beacon_minor": beacon_minor,
    }

    missing = []
    for name, value in fields.items():
        if is_blank(value):
            missing.append(name)

    if len(missing) == len(fields):
        return None

    if len(missing) > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "beacon_uuid, beacon_major and beacon_minor must be sent together; "
                f"missing: {', '.join(missing)}"
            ),
        )

    return {
        "uuid": parse_beacon_uuid(beacon_uuid),
        "major": parse_beacon_number("beacon_major", beacon_major),
        "minor": parse_beacon_number("beacon_minor", beacon_minor),
    }


def insert_photo_row(row: dict) -> dict:
    """Insert a photos row, retrying once. Raises the last error if both attempts fail."""
    try:
        return supabase.table("photos").insert(row).execute().data[0]
    except Exception:
        logger.warning("Photo insert failed, retrying once", exc_info=True)

    return supabase.table("photos").insert(row).execute().data[0]


@router.post("", status_code=201)
def create_photo(
    background_tasks: BackgroundTasks,
    image: UploadFile | None = File(None),
    captured_at: str | None = Form(None),
    beacon_uuid: str | None = Form(None),
    beacon_major: str | None = Form(None),
    beacon_minor: str | None = Form(None),
):
    # Phase 1: validate the request. Nothing has been written yet, so any
    # failure here is a plain 400. Fields are optional in the signature so a
    # missing field reaches these checks instead of FastAPI's default 422.
    if image is None:
        raise HTTPException(status_code=400, detail="image is required")

    image_bytes = image.file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="image must be 10MB or smaller")

    # Check what the file actually is, not what the client says it is, so
    # e.g. an .exe labelled image/jpeg is rejected.
    image_type = detect_image_type(image_bytes)
    if image_type not in ALLOWED_IMAGE_TYPES:
        allowed = ", ".join(ALLOWED_IMAGE_TYPES)
        raise HTTPException(status_code=400, detail=f"image must be one of: {allowed}")

    parsed_captured_at = parse_captured_at(captured_at)
    beacon = parse_beacon(beacon_uuid, beacon_major, beacon_minor)

    # Phase 2: if a beacon was sent, find its id before uploading anything.
    # A beacon is identified by its uuid, major and minor together (several
    # beacons can share a uuid), so all three are matched.
    beacon_id = None
    if beacon is not None:
        try:
            beacon_result = (
                supabase.table("beacons")
                .select("id")
                .eq("user_id", PLACEHOLDER_USER_ID)
                .eq("beacon_uuid", beacon["uuid"])
                .eq("major", beacon["major"])
                .eq("minor", beacon["minor"])
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("Beacon lookup failed")
            raise HTTPException(status_code=500, detail="Could not check beacon")

        if len(beacon_result.data) == 0:
            raise HTTPException(status_code=404, detail="beacon not found")

        beacon_id = beacon_result.data[0]["id"]

    # Phase 3: upload the image to Storage. If this fails, nothing else has
    # been written, so there is nothing to clean up.
    storage_path = f"{uuid.uuid4()}{ALLOWED_IMAGE_TYPES[image_type]}"
    photos_bucket = supabase.storage.from_(PHOTOS_BUCKET)

    try:
        photos_bucket.upload(storage_path, image_bytes, {"content-type": image_type})
    except Exception:
        logger.exception("Storage upload failed")
        raise HTTPException(status_code=502, detail="Could not upload image to storage")

    image_url = photos_bucket.get_public_url(storage_path)

    # Phase 4: insert the row, retrying once. If both attempts fail, delete
    # the uploaded file so Storage isn't left with an orphan.
    # tagging_status is left out so the database default ('pending') applies.
    new_row = {
        "user_id": PLACEHOLDER_USER_ID,
        "captured_at": parsed_captured_at.isoformat(),
        "image_url": image_url,
        "beacon_id": beacon_id,
    }

    try:
        photo = insert_photo_row(new_row)
    except Exception:
        logger.exception("Photo insert failed after retry; removing uploaded file")
        try:
            photos_bucket.remove([storage_path])
        except Exception:
            logger.exception("Could not remove orphaned file %s from storage", storage_path)
        raise HTTPException(status_code=500, detail="Could not save photo")

    # Phase 5: start tagging in the background. FastAPI runs background
    # tasks after the response is sent, so the client gets its 201 without
    # waiting on tagging.
    background_tasks.add_task(trigger_tagging, photo["id"])

    return {"id": photo["id"], "tagging_status": photo["tagging_status"]}


def get_current_user_id() -> str:
    """Return the id of the user making the request.

    Always the shared placeholder for now. When real auth arrives (COMP491),
    only this function needs to change for GET /photos.
    """
    return PLACEHOLDER_USER_ID


def created_at_of(row: dict) -> datetime:
    """The row's created_at as a datetime (Supabase returns it as a string)."""
    return datetime.fromisoformat(row["created_at"])


def is_due_for_retag(row: dict, cutoff: datetime) -> bool:
    """True if the photo failed tagging, or is still 'pending' from before cutoff."""
    if row["tagging_status"] == "failed":
        return True

    if row["tagging_status"] == "pending":
        return created_at_of(row) < cutoff

    return False


def fetch_recent_photos(user_id: str, limit: int) -> list[dict]:
    """Return the user's newest photos, newest first, at most limit of them."""
    result = (
        supabase.table("photos")
        .select(LIST_COLUMNS)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def fetch_photos_needing_retag(user_id: str, limit: int) -> list[dict]:
    """Return the user's failed and stale pending photos, newest first, at most limit of them.

    The database query only narrows to 'failed' and 'pending' rows. Which
    pending rows are old enough, the ordering and the limit are all applied
    here in Python, so the tests can check them against the fake Supabase.
    """
    result = (
        supabase.table("photos")
        .select(LIST_COLUMNS)
        .eq("user_id", user_id)
        .in_("tagging_status", ["failed", "pending"])
        .execute()
    )

    cutoff = datetime.now(timezone.utc) - STALE_PENDING_AFTER

    rows = []
    for row in result.data:
        if is_due_for_retag(row, cutoff):
            rows.append(row)

    rows.sort(key=created_at_of, reverse=True)
    return rows[:limit]


def to_photo_summary(row: dict) -> PhotoSummary:
    """Turn a photos row fetched with LIST_COLUMNS into a response item."""
    room_name = None
    if row["beacons"] is not None:
        room_name = row["beacons"]["room_name"]

    return PhotoSummary(
        id=row["id"],
        created_at=row["created_at"],
        tagging_status=row["tagging_status"],
        image_url=row["image_url"],
        room_name=room_name,
    )


@router.get("", response_model=list[PhotoSummary])
def list_photos(
    needs_retag: bool = False,
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
):
    """List the user's photos, newest first.

    With needs_retag=true, only photos whose tagging failed, or that have
    been 'pending' for longer than STALE_PENDING_AFTER, are returned.
    """
    user_id = get_current_user_id()

    try:
        if needs_retag:
            rows = fetch_photos_needing_retag(user_id, limit)
        else:
            rows = fetch_recent_photos(user_id, limit)
    except Exception:
        logger.exception("Photo list lookup failed")
        raise HTTPException(status_code=500, detail="Could not load photos")

    photo_summaries = []
    for row in rows:
        photo_summaries.append(to_photo_summary(row))

    return photo_summaries
