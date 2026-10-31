"""HTTP handlers delegate business work to the workflow."""

from fastapi import APIRouter

from ..models.review import ReviewPacket, ReviewRequest
from ..workflows.review import review

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "offline_sample_parser", "policy_version": "0.1"}


@router.post("/reviews", response_model=ReviewPacket)
def create_review(request: ReviewRequest) -> ReviewPacket:
    return review(request)
