"""LangGraph flow with selectable Nebius extraction and deterministic policy/summary."""

from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from typing import Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from ..config import settings
from ..models.review import Fact, ReviewPacket, ReviewRequest, RuleResult, StepEvent, WorkflowStatus
from ..services.extraction import extract
from ..services.nebius import ProviderError, extract_nebius
from ..services.policy import evaluate


class ReviewState(TypedDict):
    request: ReviewRequest
    terms: dict[str, Fact]
    rules: list[RuleResult]
    events: list[StepEvent]
    workflow_status: WorkflowStatus
    summary: str
    mode: Literal["offline_sample_parser", "nebius"]
    model_metadata: dict


def extraction_step(state: ReviewState):
    if state["mode"] == "nebius":
        terms, metadata = extract_nebius(state["request"])
    else:
        terms, metadata = extract(state["request"]), {"model_calls": 0}
    return {"terms": terms, "model_metadata": metadata, "events": [StepEvent(step="extract_terms")]}


def policy_step(state: ReviewState):
    return {
        "rules": evaluate(state["terms"], state["request"].submitted_on),
        "events": state["events"] + [StepEvent(step="check_policy")],
    }


def route(state: ReviewState) -> Literal["clarification", "exceptions", "ready"]:
    if any(r.status == "UNKNOWN" for r in state["rules"]):
        return "clarification"
    if any(r.status == "FLAG" for r in state["rules"]):
        return "exceptions"
    return "ready"


def routing_step(status: WorkflowStatus) -> Callable:
    def apply(state):
        return {
            "workflow_status": status,
            "events": state["events"] + [StepEvent(step="route_packet")],
        }

    return apply


def summary_step(state: ReviewState):
    flagged = [r.rule_id for r in state["rules"] if r.status == "FLAG"]
    unknown = [r.rule_id for r in state["rules"] if r.status == "UNKNOWN"]
    business = state["terms"]["business_name"].value or "The applicant"
    # A deterministic summary proves the packet contract without inventing prose.
    summary = (
        f"{business}: {len(flagged)} policy exceptions"
        f" ({', '.join(flagged) or 'none'}); {len(unknown)} rules need clarification"
        f" ({', '.join(unknown) or 'none'}). Human review is required. "
        "This packet does not approve or deny a loan."
    )
    return {"summary": summary, "events": state["events"] + [StepEvent(step="summarize_packet")]}


builder = StateGraph(ReviewState)
builder.add_node("extract", extraction_step)
builder.add_node("policy", policy_step)
builder.add_node("clarification", routing_step("NEEDS_CLARIFICATION"))
builder.add_node("exceptions", routing_step("EXCEPTIONS_FOR_REVIEW"))
builder.add_node("ready", routing_step("READY_FOR_REVIEW"))
builder.add_node("summary", summary_step)
builder.add_edge(START, "extract")
builder.add_edge("extract", "policy")
builder.add_conditional_edges(
    "policy",
    route,
    {"clarification": "clarification", "exceptions": "exceptions", "ready": "ready"},
)
for node in ["clarification", "exceptions", "ready"]:
    builder.add_edge(node, "summary")
builder.add_edge("summary", END)
graph = builder.compile()


def review(request: ReviewRequest) -> ReviewPacket:
    started = perf_counter()
    mode = settings().mode
    if mode not in {"nebius", "offline_sample_parser"}:
        raise ProviderError("EXTRACTION_MODE must be nebius or offline_sample_parser.")
    initial: ReviewState = {
        "mode": cast(Literal["nebius", "offline_sample_parser"], mode),
        "model_metadata": {},
        "request": request,
        "terms": {},
        "rules": [],
        "events": [],
        "workflow_status": "NEEDS_CLARIFICATION",
        "summary": "",
    }
    result = cast(ReviewState, graph.invoke(initial))
    return ReviewPacket(
        run_id=str(uuid4()),
        mode=result["mode"],
        model_calls=result["model_metadata"].get("model_calls", 0),
        model_metadata=result["model_metadata"],
        document_id=request.document_id,
        submitted_on=request.submitted_on,
        normalized_source=request.proposal_text,
        source_sha256=sha256(request.proposal_text.encode()).hexdigest(),
        terms=result["terms"],
        rules=result["rules"],
        workflow_status=result["workflow_status"],
        summary=result["summary"],
        events=result["events"],
        clarification_questions=[r.clarification for r in result["rules"] if r.clarification],
        next_actions=[
            r.clarification or f"Human reviewer: consider {r.rule_id}. {r.explanation}"
            for r in result["rules"]
            if r.status != "PASS"
        ]
        + ["Have a human credit reviewer review the packet."],
        elapsed_ms=round((perf_counter() - started) * 1000, 3),
        limitations=[
            "Extraction mode: "
            + result["mode"]
            + "; policy checks and summary remain deterministic.",
            "No PDF ingestion, persistence, human resume, or multi-agent model/tool loops yet.",
            "Document inclusion is proposal-reported; attachments are not verified.",
            "Calendar fiscal years only; unusual wording may be missed. Do not use for real lending.",
        ],
    )
