"""The API contract: validate inputs and make evidence and uncertainty explicit."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RuleStatus = Literal["PASS", "FLAG", "UNKNOWN"]
WorkflowStatus = Literal["NEEDS_CLARIFICATION", "EXCEPTIONS_FOR_REVIEW", "READY_FOR_REVIEW"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    submitted_on: date
    proposal_text: str = Field(min_length=100, max_length=100_000)

    @field_validator("proposal_text")
    @classmethod
    def readable_text(cls, value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        if len(value.strip()) < 100 or "\x00" in value:
            raise ValueError("Supply at least 100 characters of readable proposal text.")
        return value


class Evidence(BaseModel):
    document_id: str
    section: str
    quote: str
    start: int
    end: int


class Fact(BaseModel):
    value: str | None = None
    state: Literal["KNOWN", "MISSING", "CONFLICT"] = "MISSING"
    evidence: list[Evidence] = Field(default_factory=list)

    def require_value(self) -> str:
        """Narrow the optional value explicitly, never convert missing data to zero."""
        if self.state != "KNOWN" or self.value is None:
            raise ValueError("A known fact with a non-null value is required.")
        return self.value


class RuleResult(BaseModel):
    rule_id: str
    status: RuleStatus
    explanation: str
    field_refs: list[str]
    calculation: str | None = None
    clarification: str | None = None


class StepEvent(BaseModel):
    step: str
    status: Literal["completed"] = "completed"


class AgentRun(BaseModel):
    agent: str
    execution: Literal["nebius", "offline_test"]
    input_refs: list[str]
    tool_calls: list[dict] = Field(default_factory=list)
    output: dict = Field(default_factory=dict)
    model_calls: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    model: str = ""
    response_model: str | None = None
    prompt_version: str = ""


class ReviewPacket(BaseModel):
    run_id: str
    document_id: str
    submitted_on: date
    policy_version: Literal["0.1"] = "0.1"
    mode: Literal["offline_sample_parser", "nebius"] = "offline_sample_parser"
    normalized_source: str
    source_sha256: str
    terms: dict[str, Fact]
    rules: list[RuleResult]
    workflow_status: WorkflowStatus
    summary: str
    clarification_questions: list[str]
    next_actions: list[str]
    human_review_required: Literal[True] = True
    events: list[StepEvent]
    elapsed_ms: float
    model_calls: int = 0
    model_metadata: dict = Field(default_factory=dict)
    agent_runs: list[AgentRun] = Field(default_factory=list)
    policy_review: dict = Field(default_factory=dict)
    risk_findings: list[dict] = Field(default_factory=list)
    limitations: list[str]
