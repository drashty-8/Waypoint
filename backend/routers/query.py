import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from claude_client import client
from database import supabase


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# Shown as the room for photos that were taken without a beacon.
UNKNOWN_ROOM = "Location unknown"

NO_MATCH_RESPONSE = {"matched": False, "message": "no matching photo found"}

# Same model as tagging. It supports forced tool use (tool_choice "tool"),
# which the newest models (e.g. Claude Opus 5.5) reject with a 400.
MATCHING_MODEL = "claude-haiku-4-5-20251001"
# A match answer is well under a hundred tokens. This is only a ceiling, and
# unused tokens aren't billed, so it's set with plenty of room to spare.
MATCHING_MAX_TOKENS = 4096

MATCHING_PROMPT = (
    "You are the search step of a personal item-recall app. The user asks a "
    "question like 'where did I leave my charger?' and you pick the one photo, "
    "from the candidates given, that best answers it. Each candidate has an id, "
    "a description of what's in the photo, the room_name it was taken in, and "
    "captured_at, when it was taken."
    "\n\n"
    "Candidates are listed most-recent-first; prefer an earlier-listed (more "
    "recent) candidate when several genuinely answer the question. Use room_name "
    "when the question concerns location, not just object identity. Do not force "
    "a match — if no candidate genuinely answers the question, matched_photo_id "
    "and answer should both be null rather than guessing."
    "\n\n"
    "When you do pick a photo, answer is a short, plain sentence answering the "
    "user's question, built only from that photo's room_name and what is "
    "explicitly stated in its description. Do not add new details about the "
    "photo's contents beyond what's already written there. For example: "
    "'Your charger is in the Bedroom, based on a photo from September 26, 2026.'"
)

MATCH_TOOL = {
    "name": "record_photo_match",
    "description": "Record which candidate photo best answers the user's question, if any.",
    # strict makes the API guarantee the tool input matches this schema exactly.
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "matched_photo_id": {
                "type": ["integer", "null"],
                "description": "The id of the best-matching candidate, or null if none genuinely answers the question.",
            },
            "answer": {
                "type": ["string", "null"],
                "description": (
                    "A short, plain sentence answering the question, using only the matched "
                    "photo's room_name and its description. Null when matched_photo_id is null."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences on why this photo matched, or why nothing did.",
            },
        },
        "required": ["matched_photo_id", "answer", "reasoning"],
        "additionalProperties": False,
    },
}


class QueryRequest(BaseModel):
    # Optional here so a missing question reaches the check in ask_question
    # and gets a 400, instead of FastAPI's default 422.
    question: str | None = None


def room_name_for(row: dict) -> str:
    """Return the room name from a photos row fetched with "beacons(room_name)"."""
    if row["beacons"] is None:
        return UNKNOWN_ROOM

    return row["beacons"]["room_name"]


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
        candidates.append({
            "id": row["id"],
            "description": row["description"],
            "room_name": room_name_for(row),
            "captured_at": row["captured_at"],
        })

    return candidates


def request_match(question: str, candidates: list[dict]):
    """Send the question and candidate list to Claude and return its response."""
    user_message = (
        f"Question: {question}\n\n"
        f"Candidates (most recent first):\n{json.dumps(candidates, indent=2)}"
    )

    return client.messages.create(
        model=MATCHING_MODEL,
        max_tokens=MATCHING_MAX_TOKENS,
        system=MATCHING_PROMPT,
        tools=[MATCH_TOOL],
        # Make Claude answer by calling the tool, not with plain text.
        tool_choice={"type": "tool", "name": MATCH_TOOL["name"]},
        messages=[{"role": "user", "content": user_message}],
    )


def find_match_result(response) -> dict | None:
    """Return the tool call's input ({"matched_photo_id", "answer", "reasoning"}), or None if Claude didn't make one."""
    # Anything other than "tool_use" (e.g. "max_tokens" or "refusal") means
    # the tool call is missing or incomplete.
    if response.stop_reason != "tool_use":
        return None

    for block in response.content:
        if block.type == "tool_use" and block.name == MATCH_TOOL["name"]:
            return block.input

    return None


def fetch_matched_photo(photo_id: int) -> dict | None:
    """Return the matched photo's row with its room name, or None if there isn't one."""
    result = (
        supabase.table("photos")
        .select("id, image_url, description, captured_at, beacons(room_name)")
        .eq("id", photo_id)
        .limit(1)
        .execute()
    )

    if len(result.data) == 0:
        return None

    return result.data[0]


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

    # With nothing to search, skip the (billed) Claude call entirely.
    if len(candidates) == 0:
        return NO_MATCH_RESPONSE

    # Phase 3: ask Claude which candidate, if any, answers the question.
    try:
        response = request_match(request.question.strip(), candidates)
    except Exception:
        logger.exception("Claude matching call failed")
        raise HTTPException(status_code=502, detail="Could not match question to a photo")

    match = find_match_result(response)
    if match is None:
        logger.error("Claude did not return a match (stop_reason=%s)", response.stop_reason)
        raise HTTPException(status_code=502, detail="Could not match question to a photo")

    # reasoning is only for our logs; it's never sent to the client.
    logger.info("Query match: photo=%s reasoning=%s", match["matched_photo_id"], match["reasoning"])

    if match["matched_photo_id"] is None:
        return NO_MATCH_RESPONSE

    # The schema can't stop Claude from naming an id that wasn't in the
    # list, or leaving answer empty, so check both before trusting the match.
    candidate_ids = [candidate["id"] for candidate in candidates]
    if match["matched_photo_id"] not in candidate_ids or match["answer"] is None:
        logger.error("Claude returned an invalid match: %s", match)
        raise HTTPException(status_code=502, detail="Could not match question to a photo")

    # Phase 4: look up the matched photo's full row.
    try:
        photo = fetch_matched_photo(match["matched_photo_id"])
    except Exception:
        logger.exception("Matched photo lookup failed for photo %s", match["matched_photo_id"])
        raise HTTPException(status_code=500, detail="Could not load matched photo")

    # Only happens if the photo was deleted after the candidates were gathered.
    if photo is None:
        logger.error("Matched photo %s no longer exists", match["matched_photo_id"])
        raise HTTPException(status_code=500, detail="Could not load matched photo")

    return {
        "matched": True,
        "answer": match["answer"],
        "image_url": photo["image_url"],
        "description": photo["description"],
        "room_name": room_name_for(photo),
        "captured_at": photo["captured_at"],
    }
