"""Durable graph: reuse specialist nodes, then interrupt for human input."""

import hashlib
import json
import time
from collections.abc import Callable
from typing import TypedDict, cast
from uuid import UUID, uuid5

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from ..models.review import AgentRun, Fact, ReviewRequest, RuleResult, StepEvent, WorkflowStatus
from ..models.saved_review import HumanAction
from ..storage.review_store import ReviewConflict, now
from . import review as core


class SavedState(TypedDict):
    review_id: str
    revision: int
    created_at: str
    updated_at: str
    request: dict
    mode: str
    terms: dict
    rules: list[dict]
    events: list[dict]
    workflow_status: str
    summary: str
    agent_runs: list[dict]
    policy_review: dict
    risk_findings: list[dict]
    lifecycle_status: str
    packet: dict | None
    history: list[dict]
    actions: list[dict]
    pending_action: dict | None
    reviewer_request_note: str
    reviewed_by: str | None
    reviewed_at: str | None
    last_error: dict | None
    analysis_started_at: float


def fingerprint(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def initial_state(row: dict) -> SavedState:
    request = json.loads(row["initial_request"])
    return SavedState(
        review_id=row["review_id"],
        revision=1,
        created_at=row["created_at"],
        updated_at=row["created_at"],
        request=request,
        mode=row["mode"],
        terms={},
        rules=[],
        events=[],
        workflow_status="NEEDS_CLARIFICATION",
        summary="",
        agent_runs=[],
        policy_review={},
        risk_findings=[],
        lifecycle_status="PROCESSING",
        packet=None,
        history=[],
        pending_action=None,
        reviewer_request_note="",
        reviewed_by=None,
        reviewed_at=None,
        last_error=None,
        analysis_started_at=time.time(),
        actions=[
            {
                "action_id": row["review_id"],
                "action": "created",
                "actor": "system",
                "note": "Review created.",
                "expected_revision": 1,
                "resulting_revision": 1,
                "submitted_at": row["created_at"],
                "payload_sha256": fingerprint(request),
            }
        ],
    )


def core_state(state: SavedState) -> core.ReviewState:
    return cast(
        core.ReviewState,
        {
            "request": ReviewRequest.model_validate(state["request"]),
            "mode": state["mode"],
            "terms": {n: Fact.model_validate(f) for n, f in state["terms"].items()},
            "rules": [RuleResult.model_validate(r) for r in state["rules"]],
            "events": [StepEvent.model_validate(e) for e in state["events"]],
            "agent_runs": [AgentRun.model_validate(a) for a in state["agent_runs"]],
            "policy_review": state["policy_review"],
            "risk_findings": state["risk_findings"],
            "workflow_status": state["workflow_status"],
            "summary": state["summary"],
        },
    )


def json_state(value):
    """Only JSON primitives are checkpointed; no arbitrary Python objects."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: json_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_state(item) for item in value]
    return value


def adapted(function: Callable):
    def node(state: SavedState):
        return json_state(function(core_state(state)))

    return node


def prepare_handoff(state: SavedState):
    finished = now()
    packet = core.packet_from_state(
        core_state(state),
        str(uuid5(UUID(state["review_id"]), str(state["revision"]))),
        round((time.time() - state["analysis_started_at"]) * 1000, 3),
    ).model_dump(mode="json")
    revision = {
        "revision": state["revision"],
        "created_at": finished,
        "request": state["request"],
        "packet": packet,
    }
    return {
        "packet": packet,
        "history": state["history"] + [revision],
        "lifecycle_status": "AWAITING_CLARIFICATION"
        if state["workflow_status"] == "NEEDS_CLARIFICATION"
        else "AWAITING_REVIEW",
        "updated_at": finished,
        "last_error": None,
        "reviewer_request_note": "",
    }


def human_pause(state: SavedState):
    # No model calls or other side effects before interrupt: this node restarts
    # on resume, but the completed specialist nodes do not rerun.
    packet = state["packet"] or {}
    action = interrupt(
        {
            "review_id": state["review_id"],
            "revision": state["revision"],
            "lifecycle_status": state["lifecycle_status"],
            "questions": packet.get("clarification_questions", []),
            "reviewer_request": state["reviewer_request_note"],
            "allowed_actions": ["clarify"]
            if state["lifecycle_status"] == "AWAITING_CLARIFICATION"
            else ["mark_reviewed", "request_revision"],
        }
    )
    return {"pending_action": action}


def validate_action(state: SavedState, action: HumanAction):
    if action.expected_revision != state["revision"]:
        raise ReviewConflict(
            "Revision changed. Reload the saved review before submitting an action."
        )
    status = state["lifecycle_status"]
    if action.action == "clarify" and status != "AWAITING_CLARIFICATION":
        raise ReviewConflict("Clarification is only allowed while awaiting clarification.")
    if action.action in {"request_revision", "mark_reviewed"} and status != "AWAITING_REVIEW":
        raise ReviewConflict("This action requires a packet awaiting human review.")
    if action.action == "clarify":
        ReviewRequest.model_validate(
            {**state["request"], "proposal_text": action.replacement_proposal_text}
        )


def apply_action(state: SavedState):
    action = HumanAction.model_validate(state["pending_action"])
    validate_action(state, action)
    payload = action.model_dump(mode="json")
    revision = state["revision"] + (1 if action.action == "clarify" else 0)
    audit = {
        "action_id": str(action.action_id),
        "action": action.action,
        "actor": action.actor,
        "note": action.note,
        "expected_revision": action.expected_revision,
        "resulting_revision": revision,
        "submitted_at": now(),
        "payload_sha256": fingerprint(payload),
    }
    update = {
        "actions": state["actions"] + [audit],
        "pending_action": None,
        "updated_at": audit["submitted_at"],
    }
    if action.action == "mark_reviewed":
        return {
            **update,
            "lifecycle_status": "REVIEWED",
            "reviewed_by": action.actor,
            "reviewed_at": audit["submitted_at"],
        }
    if action.action == "request_revision":
        return {
            **update,
            "lifecycle_status": "AWAITING_CLARIFICATION",
            "reviewer_request_note": action.note,
        }
    request = ReviewRequest.model_validate(
        {**state["request"], "proposal_text": action.replacement_proposal_text}
    )
    return {
        **update,
        "request": request.model_dump(mode="json"),
        "revision": revision,
        "packet": None,
        "lifecycle_status": "PROCESSING",
        "terms": {},
        "rules": [],
        "events": [],
        "agent_runs": [],
        "summary": "",
        "risk_findings": [],
        "policy_review": {},
        "last_error": None,
        "reviewer_request_note": "",
        "analysis_started_at": time.time(),
    }


def build_saved_graph(checkpointer):
    builder = StateGraph(SavedState)
    builder.add_node("extract", adapted(core.extraction_step))
    builder.add_node("policy", adapted(core.policy_step))
    for name, status in [
        ("clarification", "NEEDS_CLARIFICATION"),
        ("exceptions", "EXCEPTIONS_FOR_REVIEW"),
        ("ready", "READY_FOR_REVIEW"),
    ]:
        builder.add_node(name, adapted(core.routing_step(cast(WorkflowStatus, status))))
    builder.add_node("summary", adapted(core.summary_step))
    builder.add_node("prepare_handoff", prepare_handoff)
    builder.add_node("human_pause", human_pause)
    builder.add_node("apply_action", apply_action)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "policy")
    builder.add_conditional_edges(
        "policy",
        lambda state: core.route(core_state(state)),
        {"clarification": "clarification", "exceptions": "exceptions", "ready": "ready"},
    )
    for name in ["clarification", "exceptions", "ready"]:
        builder.add_edge(name, "summary")
    builder.add_edge("summary", "prepare_handoff")
    builder.add_edge("prepare_handoff", "human_pause")
    builder.add_edge("human_pause", "apply_action")
    builder.add_conditional_edges(
        "apply_action",
        lambda state: (
            "extract"
            if state["lifecycle_status"] == "PROCESSING"
            else "finished"
            if state["lifecycle_status"] == "REVIEWED"
            else "human_pause"
        ),
        {"extract": "extract", "finished": END, "human_pause": "human_pause"},
    )
    return builder.compile(checkpointer=checkpointer)
