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

NO_MATCH_RESPONSE = {"matched": False, "confidence": "none", "message": "no matching photo found"}

# Used as the unclear response's message when Claude is unsure but left
# answer empty, so the client always has something to show.
UNCLEAR_FALLBACK_MESSAGE = "found a possible match, but couldn't confirm it answers the question"

# Chosen independently of the tagging model: query uses Haiku 4.5 with a
# forced tool call. It supports forced tool use (tool_choice "tool"),
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
    "when the question concerns location, not just object identity."
    "\n\n"
    "Set confidence to one of three values:\n"
    "- confident: a candidate clearly answers the question. Never use confident "
    "to cover a guess.\n"
    "- unsure: a candidate shows the kind of item the question asks about, but "
    "its description cannot confirm a detail the question asks for. For example, "
    "the question asks for a flathead screwdriver and the description only says "
    "screwdriver. A detail that the description doesn't mention is a reason to "
    "be unsure, not a reason to reject the candidate.\n"
    "- none: no candidate shows the kind of item the question asks about at all. "
    "Use none only when nothing is even a possible match, never because a "
    "detail is unconfirmed. matched_photo_id and answer are both null."
    "\n\n"
    "When confidence is confident or unsure, matched_photo_id is the chosen "
    "candidate's id and answer is a short, plain sentence answering the user's "
    "question, built only from that photo's room_name and what is explicitly "
    "stated in its description. Do not add new details about the photo's "
    "contents beyond what's already written there. For example: "
    "'Your charger is in the Bedroom, based on a photo from September 26, 2026.' "
    "When unsure, the answer must say what is uncertain. For example: 'There's "
    "a screwdriver in the Garage, based on a photo from September 26, 2026, but "
    "the photo doesn't show whether it's a flathead.'"
)

MATCH_TOOL = {
    "name": "record_photo_match",
    "description": "Record which candidate photo best answers the user's question, if any.",
    # strict makes the API guarantee the tool input matches this schema exactly.
    "strict": True,
    "input_schema": {
        "type": "object",
        # Claude fills these in top to bottom, so the order matters: it
        # reasons first, then picks a confidence level, and only then names a
        # photo. With matched_photo_id first, Claude committed to null before
        # it had weighed whether a candidate was an "unsure" match.
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (
                    "One or two sentences, written before deciding: which candidate, if any, "
                    "shows the kind of item asked about, and whether its description confirms "
                    "every detail the question asks for."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["confident", "unsure", "none"],
                "description": (
                    "confident: a candidate clearly answers the question. unsure: a candidate "
                    "shows the kind of item asked about, but its description can't confirm a "
                    "detail the question asks for. none: no candidate is even a possible "
                    "match; never use none just because a detail is unconfirmed."
                ),
            },
            "matched_photo_id": {
                "type": ["integer", "null"],
                "description": "The id of the chosen candidate, or null when confidence is none.",
            },
            "answer": {
                "type": ["string", "null"],
                "description": (
                    "A short, plain sentence answering the question, using only the matched "
                    "photo's room_name and its description. When unsure, it says what is "
                    "uncertain. Null when confidence is none."
                ),
            },
        },
        "required": ["reasoning", "confidence", "matched_photo_id", "answer"],
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
    photos.beacon_id foreign key and include the matching beacon's
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
    """Return the tool call's input ({"matched_photo_id", "answer", "confidence", "reasoning"}), or None if Claude didn't make one."""
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


def has_answer(match: dict) -> bool:
    """True if Claude's answer has actual text in it (not None, not just whitespace)."""
    if match["answer"] is None:
        return False

    return match["answer"].strip() != ""


def resolve_confidence(match: dict) -> str:
    """Return the confidence level to act on, downgrading combinations that don't add up.

    Claude's stated confidence is only trusted when the rest of its reply
    supports it:
    - "none" always stays "none".
    - "confident" or "unsure" with no photo id becomes "none".
    - "confident" with an empty answer becomes "unsure", so a confident
      match is never returned without an answer.

    The caller has already rejected ids that weren't in the candidate list,
    so any non-null id here is a valid one.
    """
    photo_id = match["matched_photo_id"]
    confidence = match["confidence"]

    if confidence == "none":
        if photo_id is not None:
            logger.warning("Claude said confidence none but named photo %s; treating as no match", photo_id)
        return "none"

    if photo_id is None:
        logger.warning("Claude said confidence %s but named no photo; downgrading to none", confidence)
        return "none"

    if confidence == "confident" and not has_answer(match):
        logger.warning("Claude was confident about photo %s but gave no answer; downgrading to unsure", photo_id)
        return "unsure"

    return confidence


def unclear_message(match: dict) -> str:
    """Return the message for an unclear response: Claude's answer, or a fallback if it's empty."""
    if has_answer(match):
        return match["answer"]

    logger.warning("Claude was unsure about photo %s but gave no answer; using fallback message", match["matched_photo_id"])
    return UNCLEAR_FALLBACK_MESSAGE


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
    logger.info(
        "Query match: photo=%s confidence=%s reasoning=%s",
        match["matched_photo_id"],
        match["confidence"],
        match["reasoning"],
    )

    # The schema can't stop Claude from naming an id that wasn't in the
    # list. That reply can't be trusted at all, so it's an error rather than
    # a downgrade. (A "none" reply ignores the id, so it's not checked.)
    candidate_ids = [candidate["id"] for candidate in candidates]
    photo_id = match["matched_photo_id"]
    if match["confidence"] != "none" and photo_id is not None and photo_id not in candidate_ids:
        logger.error("Claude returned an invalid match: %s", match)
        raise HTTPException(status_code=502, detail="Could not match question to a photo")

    confidence = resolve_confidence(match)

    if confidence == "none":
        return NO_MATCH_RESPONSE

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

    if confidence == "unsure":
        # Not a match, but the photo is offered so the user can check it themselves.
        return {
            "matched": False,
            "confidence": "unsure",
            "unclear": True,
            "message": unclear_message(match),
            "candidate": {
                "image_url": photo["image_url"],
                "room_name": room_name_for(photo),
                "captured_at": photo["captured_at"],
            },
        }

    return {
        "matched": True,
        "confidence": "confident",
        "answer": match["answer"],
        "image_url": photo["image_url"],
        "description": photo["description"],
        "room_name": room_name_for(photo),
        "captured_at": photo["captured_at"],
    }
