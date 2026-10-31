"""HTTP endpoints for durable local reviews and human actions."""

import sqlite3
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..models.review import ReviewRequest
from ..models.saved_review import (
    HumanAction,
    RetryAction,
    ReviewSummary,
    RevisionRecord,
    SavedReview,
)
from ..services.nebius import ProviderError
from ..services.saved_reviews import ReviewService, SavedRunError
from ..storage.review_store import ReviewConflict, ReviewNotFound

router = APIRouter()
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "Saved review not found"},
    409: {
        "description": "Stale revision, invalid lifecycle action, conflicting replay or active operation"
    },
    502: {"description": "Provider stage failed; review_id and accepted partial work are retained"},
    503: {"description": "Local review storage is unavailable"},
}


@contextmanager
def api_errors():
    try:
        yield
    except SavedRunError as exc:
        raise HTTPException(status_code=502, detail=exc.detail) from None
    except ReviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(
            status_code=503,
            detail="Local review storage is unavailable. Check the data directory and retry.",
        ) from None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings().mode, "policy_version": "0.1"}


@router.post("/reviews", response_model=SavedReview, responses=ERRORS)
def create_review(request: ReviewRequest) -> SavedReview:
    with api_errors():
        return ReviewService().create(request)


@router.get("/reviews", response_model=list[ReviewSummary], responses=ERRORS)
def list_reviews(limit: int = Query(20, ge=1, le=100)) -> list[ReviewSummary]:
    with api_errors():
        return ReviewService().list(limit)


@router.get("/reviews/{review_id}", response_model=SavedReview, responses=ERRORS)
def get_review(review_id: UUID) -> SavedReview:
    with api_errors():
        return ReviewService().get(str(review_id))


@router.get("/reviews/{review_id}/history", response_model=list[RevisionRecord], responses=ERRORS)
def review_history(review_id: UUID) -> list[RevisionRecord]:
    with api_errors():
        return ReviewService().history(str(review_id))


@router.post("/reviews/{review_id}/actions", response_model=SavedReview, responses=ERRORS)
def act_on_review(review_id: UUID, action: HumanAction) -> SavedReview:
    with api_errors():
        return ReviewService().act(str(review_id), action)


@router.post("/reviews/{review_id}/retry", response_model=SavedReview, responses=ERRORS)
def retry_review(review_id: UUID, action: RetryAction) -> SavedReview:
    with api_errors():
        return ReviewService().retry(str(review_id), action)
