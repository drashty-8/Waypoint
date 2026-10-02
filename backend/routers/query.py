import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import supabase


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# Shown as the room for photos that were taken without a beacon.
UNKNOWN_ROOM = "Location unknown"


class QueryRequest(BaseModel):
    # Optional here so a missing question reaches the check in ask_question
    # and gets a 400, instead of FastAPI's default 422.
    question: str | None = None


def get_candidate_photos() -> list[dict]:
    """Return every fully tagged photo with its room name, most recent first.

    "beacons(room_name)" in the select asks Supabase to follow the
    photos.beacon_uuid foreign key and include the matching beacon's
    room_name, so no second query is needed. For a photo with no beacon,
    "beacons" comes back as None.
    """
    result = (
        supabase.table("photos")
        .select("id, description, captured_at, beacons(room_name)")
        .eq("tagging_status", "complete")
        .order("captured_at", desc=True)
        .execute()
    )

    candidates = []
    for row in result.data:
        if row["beacons"] is None:
            room_name = UNKNOWN_ROOM
        else:
            room_name = row["beacons"]["room_name"]

        candidates.append({
            "id": row["id"],
            "description": row["description"],
            "room_name": room_name,
            "captured_at": row["captured_at"],
        })

    return candidates


@router.post("")
def ask_question(request: QueryRequest):
    # Phase 1: validate the request.
    if request.question is None or request.question.strip() == "":
        raise HTTPException(status_code=400, detail="question is required")

    # Phase 2: gather the photos the question could match.
    try:
        candidates = get_candidate_photos()
    except Exception:
        logger.exception("Candidate photo lookup failed")
        raise HTTPException(status_code=500, detail="Could not load photos")

    # For now, return the candidates directly so this step can be tested
    # before the Claude matching call exists.
    return candidates
