"""Saved lifecycle service: checkpointed graphs, revision guards and action replay."""

from contextlib import contextmanager
from pathlib import Path
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from ..config import review_data_directory, settings
from ..models.review import ReviewRequest
from ..models.saved_review import (
    HumanAction,
    RetryAction,
    ReviewSummary,
    RevisionRecord,
    SavedReview,
)
from ..storage.review_store import ReviewConflict, ReviewStore, now
from ..workflows.errors import WorkflowError
from ..workflows.saved_review import (
    SavedState,
    build_saved_graph,
    fingerprint,
    initial_state,
    validate_action,
)


class SavedRunError(Exception):
    def __init__(self, detail: dict):
        super().__init__(detail["message"])
        self.detail = detail


class ReviewService:
    def __init__(self, directory: Path | None = None):
        self.store = ReviewStore(directory or review_data_directory())

    @contextmanager
    def graph(self, review_id: str):
        row = self.store.get(review_id)
        with SqliteSaver.from_conn_string(str(self.store.path)) as saver:
            graph = build_saved_graph(saver)
            config: RunnableConfig = {
                "configurable": {"thread_id": review_id},
                "recursion_limit": 40,
            }
            yield graph, config, row

    def state(self, graph, config, row):
        snapshot = graph.get_state(config)
        return snapshot, cast(SavedState, snapshot.values or initial_state(row))

    def record(self, graph, config, row) -> SavedReview:
        snapshot, state = self.state(graph, config, row)
        interrupts = [item.value for item in snapshot.interrupts]
        return SavedReview.model_validate(
            {
                "review_id": row["review_id"],
                "revision": state["revision"],
                "lifecycle_status": state["lifecycle_status"],
                "created_at": row["created_at"],
                "updated_at": state["updated_at"],
                "current_request": state["request"],
                "packet": state["packet"],
                "pending_interrupt": interrupts[0] if interrupts else None,
                "revision_history": [
                    {
                        "revision": h["revision"],
                        "created_at": h["created_at"],
                        "run_id": h["packet"]["run_id"],
                        "source_sha256": h["packet"]["source_sha256"],
                        "workflow_status": h["packet"]["workflow_status"],
                    }
                    for h in state["history"]
                ],
                "actions": state["actions"],
                "reviewed_by": state["reviewed_by"],
                "reviewed_at": state["reviewed_at"],
                "last_error": state["last_error"],
            }
        )

    def execute(self, graph, config, row, command):
        try:
            graph.invoke(command, config, durability="sync")
        except WorkflowError as exc:
            _, state = self.state(graph, config, row)
            detail = {
                "review_id": row["review_id"],
                "revision": state["revision"],
                "message": str(exc),
                "stage": exc.stage,
                "workflow_status": "ERROR_NEEDS_REVIEW",
                "partial_packet": exc.partial,
            }
            graph.update_state(
                config,
                {
                    "lifecycle_status": "ERROR_NEEDS_REVIEW",
                    "last_error": detail,
                    "updated_at": now(),
                },
            )
            raise SavedRunError(detail) from None

    def create(self, request: ReviewRequest) -> SavedReview:
        mode = settings().mode
        if mode not in {"nebius", "offline_sample_parser"}:
            raise ReviewConflict("Configure a supported extraction mode before creating reviews.")
        row = self.store.create(request.model_dump(mode="json"), mode)
        review_id = row["review_id"]
        with self.store.claim(review_id), self.graph(review_id) as (graph, config, row):
            self.execute(graph, config, row, initial_state(row))
            return self.record(graph, config, row)

    def get(self, review_id: str) -> SavedReview:
        with self.graph(review_id) as (graph, config, row):
            return self.record(graph, config, row)

    def history(self, review_id: str) -> list[RevisionRecord]:
        with self.graph(review_id) as (graph, config, row):
            _, state = self.state(graph, config, row)
            return [RevisionRecord.model_validate(item) for item in state["history"]]

    def list(self, limit: int) -> list[ReviewSummary]:
        records = [self.get(review_id) for review_id in self.store.list_ids(limit)]
        return [
            ReviewSummary.model_validate(
                {
                    "review_id": r.review_id,
                    "document_id": r.current_request.document_id,
                    "revision": r.revision,
                    "lifecycle_status": r.lifecycle_status,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
            )
            for r in records
        ]

    def duplicate(self, state, payload: dict) -> bool:
        for event in state["actions"]:
            if event["action_id"] == str(payload["action_id"]):
                if event["payload_sha256"] != fingerprint(payload):
                    raise ReviewConflict(
                        "This action_id was already used with a different payload."
                    )
                return True
        return False

    def act(self, review_id: str, action: HumanAction) -> SavedReview:
        payload = action.model_dump(mode="json")
        with self.store.claim(review_id), self.graph(review_id) as (graph, config, row):
            snapshot, state = self.state(graph, config, row)
            if self.duplicate(state, payload):
                return self.record(graph, config, row)
            pending = state["pending_action"]
            # Recover a resume accepted by the graph before a process stopped,
            # but not yet applied. Do not send a second interrupt resume value.
            if pending is not None:
                if fingerprint(pending) != fingerprint(payload):
                    raise ReviewConflict(
                        "Another action is already queued; retry the original action or recover the run."
                    )
                self.execute(graph, config, row, None)
            else:
                validate_action(state, action)
                if not snapshot.interrupts:
                    raise ReviewConflict(
                        "Review is not paused. Use retry for an interrupted processing run."
                    )
                self.execute(graph, config, row, Command(resume=payload))
            return self.record(graph, config, row)

    def retry(self, review_id: str, action: RetryAction) -> SavedReview:
        payload = {**action.model_dump(mode="json"), "action": "retry"}
        with self.store.claim(review_id), self.graph(review_id) as (graph, config, row):
            snapshot, state = self.state(graph, config, row)
            if self.duplicate(state, payload):
                return self.record(graph, config, row)
            if action.expected_revision != state["revision"]:
                raise ReviewConflict("Revision changed. Reload before retrying.")
            if (
                state["lifecycle_status"] not in {"ERROR_NEEDS_REVIEW", "PROCESSING"}
                or snapshot.interrupts
            ):
                raise ReviewConflict(
                    "Retry is only for a failed or interrupted processing run, not a human pause."
                )
            event = {
                "action_id": str(action.action_id),
                "action": "retry",
                "actor": action.actor,
                "note": action.note,
                "expected_revision": action.expected_revision,
                "resulting_revision": state["revision"],
                "submitted_at": now(),
                "payload_sha256": fingerprint(payload),
            }
            if not snapshot.values:
                recovered = initial_state(row)
                recovered["actions"] = recovered["actions"] + [event]
                self.execute(graph, config, row, recovered)
            else:
                graph.update_state(
                    config,
                    {
                        "actions": state["actions"] + [event],
                        "lifecycle_status": "PROCESSING",
                        "last_error": None,
                        "updated_at": event["submitted_at"],
                    },
                )
                self.execute(graph, config, row, None)
            return self.record(graph, config, row)
