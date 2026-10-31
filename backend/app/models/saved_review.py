"""Saved-review API contracts separate packet decisions from human workflow state."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .review import ReviewPacket, ReviewRequest

LifecycleStatus = Literal[
    "PROCESSING", "AWAITING_CLARIFICATION", "AWAITING_REVIEW", "REVIEWED", "ERROR_NEEDS_REVIEW"
]


class HumanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    expected_revision: int = Field(ge=1)
    action: Literal["clarify", "request_revision", "mark_reviewed"]
    actor: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=1, max_length=2000)
    replacement_proposal_text: str | None = Field(default=None, min_length=100, max_length=100_000)

    @field_validator("actor", "note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Use a nonblank actor and note.")
        return value

    @model_validator(mode="after")
    def corrected_source(self):
        if self.action == "clarify" and not self.replacement_proposal_text:
            raise ValueError("clarify requires the complete corrected proposal text.")
        if self.action != "clarify" and self.replacement_proposal_text is not None:
            raise ValueError("Only clarify accepts replacement_proposal_text.")
        return self

    @field_validator("replacement_proposal_text")
    @classmethod
    def readable_proposal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        if len(value.strip()) < 100 or "\x00" in value:
            raise ValueError("Provide the complete readable corrected proposal.")
        return value


class RetryAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    expected_revision: int = Field(ge=1)
    actor: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("actor", "note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Actor and note cannot be blank.")
        return value.strip()


class AuditEntry(BaseModel):
    action_id: str
    action: str
    actor: str
    note: str
    expected_revision: int
    resulting_revision: int
    submitted_at: datetime
    payload_sha256: str


class RevisionRecord(BaseModel):
    revision: int
    created_at: datetime
    request: ReviewRequest
    packet: ReviewPacket


class RevisionInfo(BaseModel):
    revision: int
    created_at: datetime
    run_id: str
    source_sha256: str
    workflow_status: str


class SavedReview(BaseModel):
    review_id: str
    revision: int
    lifecycle_status: LifecycleStatus
    created_at: datetime
    updated_at: datetime
    current_request: ReviewRequest
    packet: ReviewPacket | None
    pending_interrupt: dict | None
    revision_history: list[RevisionInfo]
    actions: list[AuditEntry]
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    last_error: dict | None = None


class ReviewSummary(BaseModel):
    review_id: str
    document_id: str
    revision: int
    lifecycle_status: LifecycleStatus
    created_at: datetime
    updated_at: datetime
