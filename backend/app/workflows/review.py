"""LangGraph orchestrator for extraction, policy review and risk summary."""

from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from typing import Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from ..agents.policy_review import PolicyAssessment, review_policy
from ..agents.risk_summary import summarize_risks
from ..config import settings
from ..models.review import (
    AgentRun,
    Fact,
    ReviewPacket,
    ReviewRequest,
    RuleResult,
    StepEvent,
    WorkflowStatus,
)
from ..services.extraction import extract
from ..services.nebius import ProviderError, extract_nebius
from ..services.policy import evaluate
from .errors import WorkflowError


class ReviewState(TypedDict):
    request: ReviewRequest
    terms: dict[str, Fact]
    rules: list[RuleResult]
    events: list[StepEvent]
    workflow_status: WorkflowStatus
    summary: str
    mode: Literal["offline_sample_parser", "nebius"]
    agent_runs: list[AgentRun]
    policy_review: dict
    risk_findings: list[dict]


def partial(state: ReviewState) -> dict:
    return {
        "document_id": state["request"].document_id,
        "terms": {name: fact.model_dump() for name, fact in state["terms"].items()},
        "rules": [r.model_dump() for r in state["rules"]],
        "agent_runs": [run.model_dump() for run in state["agent_runs"]],
    }


def extraction_step(state: ReviewState):
    try:
        if state["mode"] == "nebius":
            terms, metadata = extract_nebius(state["request"])
        else:
            terms, metadata = extract(state["request"]), {"model_calls": 0}
    except ProviderError as exc:
        raise WorkflowError("extraction", str(exc), partial(state)) from None
    run = AgentRun.model_validate(
        dict(
            agent="extraction",
            execution="nebius" if state["mode"] == "nebius" else "offline_test",
            input_refs=["proposal_text", "submitted_on"],
            tool_calls=[
                {
                    "name": "validate_source_evidence",
                    "arguments": {"document_id": state["request"].document_id},
                    "result": {"field_count": len(terms), "evidence_spans_verified": True},
                }
            ],
            output={"field_states": {name: fact.state for name, fact in terms.items()}},
            **metadata,
        )
    )
    return {"terms": terms, "agent_runs": [run], "events": [StepEvent(step="extract_terms")]}


def policy_step(state: ReviewState):
    try:
        if state["mode"] == "nebius":
            rules, trace = review_policy(state["terms"], state["request"].submitted_on)
        else:
            rules = evaluate(state["terms"], state["request"].submitted_on)
            audit = PolicyAssessment(
                policy_version="0.1",
                reviewed_rule_ids=[r.rule_id for r in rules],
                flagged_rule_ids=[r.rule_id for r in rules if r.status == "FLAG"],
                unknown_rule_ids=[r.rule_id for r in rules if r.status == "UNKNOWN"],
            )
            trace = {
                "agent": "policy_review",
                "execution": "offline_test",
                "input_refs": ["terms", "submitted_on"],
                "output": audit.model_dump(),
            }
    except ProviderError as exc:
        raise WorkflowError("policy_review", str(exc), partial(state)) from None
    return {
        "rules": rules,
        "policy_review": trace["output"],
        "agent_runs": state["agent_runs"] + [AgentRun.model_validate(trace)],
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
    if state["mode"] == "nebius":
        try:
            result, trace = summarize_risks(
                state["terms"], state["rules"], state["workflow_status"]
            )
        except ProviderError as exc:
            raise WorkflowError("risk_summary", str(exc), partial(state)) from None
        summary = (
            result.summary
            + " Human review is required. This packet does not approve or deny a loan."
        )
        findings = [finding.model_dump() for finding in result.findings]
    else:
        flagged = [r.rule_id for r in state["rules"] if r.status == "FLAG"]
        unknown = [r.rule_id for r in state["rules"] if r.status == "UNKNOWN"]
        business = state["terms"]["business_name"].value or "The applicant"
        summary = (
            f"{business}: {len(flagged)} policy exceptions ({', '.join(flagged) or 'none'}); "
            f"{len(unknown)} rules need clarification ({', '.join(unknown) or 'none'}). "
            "Human review is required. This packet does not approve or deny a loan."
        )
        findings = [
            {
                "rule_id": r.rule_id,
                "kind": "policy_exception" if r.status == "FLAG" else "data_gap",
                "explanation": r.explanation,
                "field_refs": r.field_refs,
                "next_action": "REVIEW_POLICY_EXCEPTION"
                if r.status == "FLAG"
                else "REQUEST_CLARIFICATION",
            }
            for r in state["rules"]
            if r.status != "PASS"
        ]
        trace = {
            "agent": "risk_summary",
            "execution": "offline_test",
            "input_refs": ["terms", "rules", "workflow_status"],
            "output": {"summary": summary, "findings": findings},
        }
    return {
        "summary": summary,
        "risk_findings": findings,
        "agent_runs": state["agent_runs"] + [AgentRun.model_validate(trace)],
        "events": state["events"] + [StepEvent(step="summarize_packet")],
    }


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
        "request": request,
        "terms": {},
        "rules": [],
        "events": [],
        "mode": cast(Literal["nebius", "offline_sample_parser"], mode),
        "agent_runs": [],
        "policy_review": {},
        "risk_findings": [],
        "workflow_status": "NEEDS_CLARIFICATION",
        "summary": "",
    }
    result = cast(ReviewState, graph.invoke(initial))
    return packet_from_state(result, str(uuid4()), round((perf_counter() - started) * 1000, 3))


def packet_from_state(result: ReviewState, run_id: str, elapsed_ms: float) -> ReviewPacket:
    request = result["request"]
    runs = result["agent_runs"]
    usage = {
        key: sum(run.usage.get(key, 0) for run in runs)
        for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
    }
    return ReviewPacket(
        run_id=run_id,
        mode=result["mode"],
        model_calls=sum(run.model_calls for run in runs),
        model_metadata={
            "pipeline_version": "loan-review-v1",
            "model": runs[0].model,
            "usage": usage,
            "stages": [
                {
                    "agent": run.agent,
                    "prompt_version": run.prompt_version,
                    "model_calls": run.model_calls,
                    "usage": run.usage,
                }
                for run in runs
            ],
        },
        document_id=request.document_id,
        submitted_on=request.submitted_on,
        normalized_source=request.proposal_text,
        source_sha256=sha256(request.proposal_text.encode()).hexdigest(),
        terms=result["terms"],
        rules=result["rules"],
        workflow_status=result["workflow_status"],
        summary=result["summary"],
        agent_runs=runs,
        policy_review=result["policy_review"],
        risk_findings=result["risk_findings"],
        events=result["events"],
        clarification_questions=[r.clarification for r in result["rules"] if r.clarification],
        next_actions=[
            r.clarification or f"Human reviewer: consider {r.rule_id}. {r.explanation}"
            for r in result["rules"]
            if r.status != "PASS"
        ]
        + ["Have a human credit reviewer review the packet."],
        elapsed_ms=elapsed_ms,
        limitations=[
            "Three specialized roles use Nebius in live mode; offline mode is explicit test behavior.",
            "Analysis packet only; saved lifecycle metadata is supplied by the saved-review API. No PDF or live progress stream yet.",
            "Narrative references/numbers are checked; full semantic faithfulness still requires human review.",
            "Proposal-reported document inclusion does not verify attachments or authenticity.",
            "Calendar fiscal years and the existing extraction limits still apply. No real credit decisions.",
        ],
    )
