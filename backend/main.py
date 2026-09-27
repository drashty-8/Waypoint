import logging
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
import filetype
from supabase import create_client

from tagging import trigger_tagging


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

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

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}


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


def parse_beacon_uuid(value: str | None) -> str | None:
    """Return beacon_uuid in standard form, None if it wasn't sent, or raise a 400 if it's invalid."""
    if value is None or value.strip() == "":
        return None

    try:
        return str(uuid.UUID(value.strip()))
    except ValueError:
        raise HTTPException(status_code=400, detail="beacon_uuid must be a valid UUID")


def insert_photo_row(row: dict) -> dict:
    """Insert a photos row, retrying once. Raises the last error if both attempts fail."""
    try:
        return supabase.table("photos").insert(row).execute().data[0]
    except Exception:
        logger.warning("Photo insert failed, retrying once", exc_info=True)

    return supabase.table("photos").insert(row).execute().data[0]


@app.post("/photos", status_code=201)
def create_photo(
    background_tasks: BackgroundTasks,
    image: UploadFile | None = File(None),
    captured_at: str | None = Form(None),
    beacon_uuid: str | None = Form(None),
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
    parsed_beacon_uuid = parse_beacon_uuid(beacon_uuid)

    # Phase 2: if a beacon was sent, make sure it exists before uploading
    # anything. Otherwise the foreign key would only fail at insert time,
    # after the file was already in Storage.
    if parsed_beacon_uuid is not None:
        try:
            beacon_result = (
                supabase.table("beacons")
                .select("id")
                .eq("beacon_uuid", parsed_beacon_uuid)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("Beacon lookup failed")
            raise HTTPException(status_code=500, detail="Could not check beacon_uuid")

        if len(beacon_result.data) == 0:
            raise HTTPException(status_code=404, detail="beacon_uuid not found")

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
        "beacon_uuid": parsed_beacon_uuid,
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
