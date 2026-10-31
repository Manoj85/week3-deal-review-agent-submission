"""Real SQLite checkpoints and interrupts, with offline analysis and isolated data."""

import json
import os
import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.saved_reviews import ReviewService
from backend.app.workflows import review as core
from backend.app.workflows.errors import WorkflowError
from backend.run_sample import ROOT, sample_request

client = TestClient(app)


def create(missing=False):
    request = sample_request().model_dump(mode="json")
    if missing:
        request["proposal_text"] = request["proposal_text"].replace(
            "annual proposed debt service is USD 24,000",
            "annual proposed debt service is not provided",
        )
    response = client.post("/reviews", json=request)
    assert response.status_code == 200, response.text
    return response.json()


def action(kind, revision=1, **extra):
    return {
        "action_id": str(uuid4()),
        "expected_revision": revision,
        "action": kind,
        "actor": "Training Reviewer",
        "note": "Checked the packet and its supporting evidence.",
        **extra,
    }


def test_create_is_a_real_saved_interrupt_and_reads_do_not_rerun(monkeypatch):
    record = create()
    review_id = record["review_id"]
    assert record["revision"] == 1
    assert record["lifecycle_status"] == "AWAITING_REVIEW"
    assert record["pending_interrupt"]["allowed_actions"] == ["mark_reviewed", "request_revision"]
    with ReviewService().graph(review_id) as (graph, config, row):
        snapshot = graph.get_state(config)
        assert snapshot.interrupts and snapshot.next == ("human_pause",)

    def no_analysis(*args):
        raise AssertionError("A read must not rerun analysis.")

    monkeypatch.setattr(core, "extraction_step", no_analysis)
    loaded = client.get("/reviews/" + review_id)
    assert loaded.status_code == 200
    assert loaded.json()["packet"]["run_id"] == record["packet"]["run_id"]
    assert client.get("/reviews").json()[0]["review_id"] == review_id
    assert len(client.get(f"/reviews/{review_id}/history").json()) == 1


def test_mark_reviewed_is_idempotent_and_does_not_change_policy(monkeypatch):
    record = create()

    def no_analysis(*args):
        raise AssertionError("Mark reviewed must not call models.")

    monkeypatch.setattr(core, "extraction_step", no_analysis)
    payload = action("mark_reviewed")
    url = f"/reviews/{record['review_id']}/actions"
    response = client.post(url, json=payload)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["lifecycle_status"] == "REVIEWED"
    assert reviewed["reviewed_by"] == "Training Reviewer"
    assert reviewed["pending_interrupt"] is None
    assert reviewed["packet"] == record["packet"]
    replay = client.post(url, json=payload)
    assert replay.status_code == 200
    assert replay.json()["actions"] == reviewed["actions"]
    assert client.post(url, json=action("mark_reviewed")).status_code == 409


def test_clarification_creates_immutable_revision_and_pins_mode(monkeypatch):
    record = create(missing=True)
    assert record["lifecycle_status"] == "AWAITING_CLARIFICATION"
    old = record["packet"]
    monkeypatch.setenv("EXTRACTION_MODE", "nebius")
    payload = action("clarify", replacement_proposal_text=sample_request().proposal_text)
    url = f"/reviews/{record['review_id']}/actions"
    response = client.post(url, json=payload)
    assert response.status_code == 200, response.text
    corrected = response.json()
    assert corrected["revision"] == 2
    assert corrected["lifecycle_status"] == "AWAITING_REVIEW"
    assert corrected["packet"]["mode"] == "offline_sample_parser"
    assert corrected["packet"]["source_sha256"] != old["source_sha256"]
    history = client.get(f"/reviews/{record['review_id']}/history").json()
    assert history[0]["packet"] == old
    assert history[1]["packet"] == corrected["packet"]
    assert "not provided" in history[0]["request"]["proposal_text"]
    assert history[1]["request"]["proposal_text"] == sample_request().proposal_text
    replay = client.post(url, json=payload)
    assert replay.status_code == 200 and replay.json()["revision"] == 2
    assert len(replay.json()["revision_history"]) == 2
    assert (
        client.post(url, json={**payload, "note": "Different payload with reused ID."}).status_code
        == 409
    )
    assert client.post(url, json=action("mark_reviewed", revision=1)).status_code == 409


def test_reviewer_requests_revision_then_analyst_corrects():
    record = create()
    url = f"/reviews/{record['review_id']}/actions"
    response = client.post(
        url, json=action("request_revision", note="Please verify the revenue figure.")
    )
    assert response.status_code == 200, response.text
    waiting = response.json()
    assert waiting["revision"] == 1
    assert waiting["lifecycle_status"] == "AWAITING_CLARIFICATION"
    assert waiting["pending_interrupt"]["reviewer_request"] == "Please verify the revenue figure."
    assert waiting["packet"] == record["packet"]
    corrected = sample_request().proposal_text.replace("USD 400,000", "USD 480,000")
    response = client.post(url, json=action("clarify", replacement_proposal_text=corrected))
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    assert (
        next(r for r in response.json()["packet"]["rules"] if r["rule_id"] == "P03")["status"]
        == "PASS"
    )


def test_unresolved_clarification_cannot_be_marked_reviewed():
    record = create(missing=True)
    url = f"/reviews/{record['review_id']}/actions"
    assert client.post(url, json=action("mark_reviewed")).status_code == 409
    assert client.post(url, json=action("clarify")).status_code == 422
    assert client.post(url, json=action("approve")).status_code == 422
    unchanged = client.get("/reviews/" + record["review_id"]).json()
    assert unchanged["lifecycle_status"] == "AWAITING_CLARIFICATION"
    assert len(unchanged["actions"]) == 1


def test_paused_review_survives_a_separate_python_process():
    record = create()
    payload = action("mark_reviewed")
    script = """
import json,sys
from backend.app.services.saved_reviews import ReviewService
from backend.app.models.saved_review import HumanAction
from backend.app.workflows import review as core
def no_analysis(*args): raise AssertionError('No model rerun after restart')
core.extraction_step=no_analysis
service=ReviewService()
before=service.get(sys.argv[1])
after=service.act(sys.argv[1],HumanAction.model_validate_json(sys.argv[2]))
print(json.dumps({'run_id':before.packet.run_id,'status':after.lifecycle_status,'revision':after.revision}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, record["review_id"], json.dumps(payload)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output == {"run_id": record["packet"]["run_id"], "status": "REVIEWED", "revision": 1}
    assert client.get("/reviews/" + record["review_id"]).json()["lifecycle_status"] == "REVIEWED"


def test_saved_failure_retries_only_failed_stage_and_replay_is_safe(monkeypatch):
    counts = {"extract": 0, "policy": 0, "summary": 0}
    originals = (core.extraction_step, core.policy_step, core.summary_step)

    def extraction(state):
        counts["extract"] += 1
        return originals[0](state)

    def policy(state):
        counts["policy"] += 1
        return originals[1](state)

    def summary(state):
        counts["summary"] += 1
        if counts["summary"] == 1:
            raise WorkflowError("risk_summary", "Temporary test failure.", core.partial(state))
        return originals[2](state)

    monkeypatch.setattr(core, "extraction_step", extraction)
    monkeypatch.setattr(core, "policy_step", policy)
    monkeypatch.setattr(core, "summary_step", summary)
    response = client.post("/reviews", json=sample_request().model_dump(mode="json"))
    assert response.status_code == 502, response.text
    review_id = response.json()["detail"]["review_id"]
    failed = client.get("/reviews/" + review_id).json()
    assert failed["lifecycle_status"] == "ERROR_NEEDS_REVIEW"
    assert failed["last_error"]["stage"] == "risk_summary"
    assert failed["packet"] is None
    payload = {k: v for k, v in action("mark_reviewed").items() if k != "action"}
    response = client.post(f"/reviews/{review_id}/retry", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["lifecycle_status"] == "AWAITING_REVIEW"
    assert counts == {"extract": 1, "policy": 1, "summary": 2}
    assert client.post(f"/reviews/{review_id}/retry", json=payload).status_code == 200
    assert counts == {"extract": 1, "policy": 1, "summary": 2}
    assert len(client.get(f"/reviews/{review_id}/history").json()) == 1


def test_active_operation_conflicts_across_service_instances():
    record = create()
    first = ReviewService()
    with first.store.claim(record["review_id"]):
        response = client.post(
            f"/reviews/{record['review_id']}/actions", json=action("mark_reviewed")
        )
        assert response.status_code == 409
    assert (
        client.post(
            f"/reviews/{record['review_id']}/actions", json=action("mark_reviewed")
        ).status_code
        == 200
    )


def test_missing_id_and_bad_action_requests():
    assert client.get("/reviews/" + str(uuid4())).status_code == 404
    assert client.get("/reviews/not-a-uuid").status_code == 422
    record = create()
    payload = action("mark_reviewed", actor="  ")
    assert client.post(f"/reviews/{record['review_id']}/actions", json=payload).status_code == 422
    assert client.get("/reviews?limit=101").status_code == 422


def test_retry_before_first_checkpoint_is_idempotent():
    service = ReviewService()
    row = service.store.create(sample_request().model_dump(mode="json"), "offline_sample_parser")
    payload = {k: v for k, v in action("mark_reviewed").items() if k != "action"}
    url = f"/reviews/{row['review_id']}/retry"
    response = client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["lifecycle_status"] == "AWAITING_REVIEW"
    assert [a["action"] for a in response.json()["actions"]] == ["created", "retry"]
    assert (
        client.post(url, json=payload).json()["packet"]["run_id"]
        == response.json()["packet"]["run_id"]
    )


def test_failed_second_revision_keeps_first_history_and_resumes(monkeypatch):
    record = create(missing=True)
    original = core.summary_step
    failures = []

    def fail_once(state):
        if not failures:
            failures.append(True)
            raise WorkflowError(
                "risk_summary", "Test failure on corrected revision.", core.partial(state)
            )
        return original(state)

    monkeypatch.setattr(core, "summary_step", fail_once)
    payload = action("clarify", replacement_proposal_text=sample_request().proposal_text)
    url = f"/reviews/{record['review_id']}"
    response = client.post(url + "/actions", json=payload)
    assert response.status_code == 502
    failed = client.get(url).json()
    assert failed["revision"] == 2 and failed["lifecycle_status"] == "ERROR_NEEDS_REVIEW"
    assert len(failed["revision_history"]) == 1
    assert client.get(url + "/history").json()[0]["packet"] == record["packet"]
    retry = {k: v for k, v in action("mark_reviewed", revision=2).items() if k != "action"}
    resumed = client.post(url + "/retry", json=retry)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["revision"] == 2
    assert len(resumed.json()["revision_history"]) == 2
    assert client.post(url + "/actions", json=payload).json()["revision"] == 2
