"""HTTP handlers delegate business work to the workflow."""

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models.review import ReviewPacket, ReviewRequest
from ..services.nebius import ProviderError
from ..workflows.errors import WorkflowError
from ..workflows.review import review

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings().mode, "policy_version": "0.1"}


@router.post("/reviews", response_model=ReviewPacket)
def create_review(request: ReviewRequest) -> ReviewPacket:
    try:
        return review(request)
    except WorkflowError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "stage": exc.stage,
                "workflow_status": "ERROR_NEEDS_REVIEW",
                "partial_packet": exc.partial,
            },
        ) from None
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
