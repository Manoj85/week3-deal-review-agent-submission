"""Run the complete graph from the repo root: python -m backend.run_sample."""

import json
from datetime import date
from pathlib import Path

from .app.models.review import ReviewRequest
from .app.workflows.review import review

ROOT = Path(__file__).resolve().parents[1]


def sample_request() -> ReviewRequest:
    return ReviewRequest(
        document_id="SAMPLE-001",
        submitted_on=date(2026, 10, 30),
        proposal_text=(ROOT / "data/proposals/sample-001.md").read_text(encoding="utf-8"),
    )


if __name__ == "__main__":
    packet = review(sample_request())
    output = ROOT / "work/checkpoint-01"
    output.mkdir(parents=True, exist_ok=True)
    (output / "sample-request.json").write_text(
        sample_request().model_dump_json(indent=2), encoding="utf-8"
    )
    (output / "sample-review.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "workflow_status": packet.workflow_status,
                "rules": {r.rule_id: r.status for r in packet.rules},
                "summary": packet.summary,
                "elapsed_ms": packet.elapsed_ms,
                "saved_to": str(output / "sample-review.json"),
            },
            indent=2,
        )
    )
