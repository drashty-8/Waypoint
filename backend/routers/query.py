from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    # Optional here so a missing question reaches the check in ask_question
    # and gets a 400, instead of FastAPI's default 422.
    question: str | None = None


@router.post("")
def ask_question(request: QueryRequest):
    # Phase 1: validate the request.
    if request.question is None or request.question.strip() == "":
        raise HTTPException(status_code=400, detail="question is required")

    # Placeholder until the matching logic exists, so the route can be
    # tested end to end.
    return {"matched_photo_id": None, "message": "not yet implemented"}
