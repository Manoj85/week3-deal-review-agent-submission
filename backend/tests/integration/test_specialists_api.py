"""Complete API/graph behavior with mocked provider decisions."""

import json

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.agent_client import AgentClient
from backend.app.services.extraction import extract
from backend.app.services.nebius import ProviderError
from backend.app.services.policy import evaluate
from backend.run_sample import sample_request
from backend.tests.helpers import risk_payload


def test_policy_failure_preserves_extraction_and_never_runs_summary(monkeypatch):
    import backend.app.workflows.review as workflow

    monkeypatch.setenv("EXTRACTION_MODE", "nebius")
    monkeypatch.setattr(
        workflow, "extract_nebius", lambda request: (extract(request), {"model_calls": 1})
    )

    def fail(*args):
        raise ProviderError("Test policy agent unavailable.")

    def must_not_run(*args):
        raise AssertionError("Summary must not run after failure.")

    monkeypatch.setattr(workflow, "review_policy", fail)
    monkeypatch.setattr(workflow, "summarize_risks", must_not_run)
    response = TestClient(app).post("/reviews", json=sample_request().model_dump(mode="json"))
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["stage"] == "policy_review"
    assert detail["workflow_status"] == "ERROR_NEEDS_REVIEW"
    assert detail["partial_packet"]["terms"]["requested_amount"]["value"] == "120000"
    assert detail["partial_packet"]["rules"] == []


def test_risk_failure_preserves_completed_rules_and_agents(monkeypatch):
    import backend.app.workflows.review as workflow

    monkeypatch.setenv("EXTRACTION_MODE", "nebius")
    monkeypatch.setattr(
        workflow, "extract_nebius", lambda request: (extract(request), {"model_calls": 1})
    )

    def policy(terms, submitted_on):
        rules = evaluate(terms, submitted_on)
        return rules, {
            "agent": "policy_review",
            "execution": "nebius",
            "input_refs": ["terms"],
            "output": {"reviewed_rule_ids": [r.rule_id for r in rules]},
            "model_calls": 1,
        }

    def fail(*args):
        raise ProviderError("Test risk agent unavailable.")

    monkeypatch.setattr(workflow, "review_policy", policy)
    monkeypatch.setattr(workflow, "summarize_risks", fail)
    response = TestClient(app).post("/reviews", json=sample_request().model_dump(mode="json"))
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["stage"] == "risk_summary"
    assert len(detail["partial_packet"]["rules"]) == 6
    assert [a["agent"] for a in detail["partial_packet"]["agent_runs"]] == [
        "extraction",
        "policy_review",
    ]


def test_tool_agents_execute_real_python_tools_and_total_usage(monkeypatch):
    import backend.app.workflows.review as workflow

    monkeypatch.setenv("EXTRACTION_MODE", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-only-key")
    monkeypatch.setenv("NEBIUS_CHAT_MODEL", "test-model")

    def extraction(request):
        return extract(request), {
            "model_calls": 1,
            "usage": {"total_tokens": 10},
            "model": "test-model",
        }

    monkeypatch.setattr(workflow, "extract_nebius", extraction)

    def chat(self, messages, **options):
        self.calls += 1
        self.usage["total_tokens"] += 10
        schema = options["response_format"]["json_schema"]
        if schema["name"].endswith("_tool_action"):
            name = schema["schema"]["properties"]["tool"]["enum"][0]
            return {"content": json.dumps({"tool": name, "arguments": {}})}
        tool_outputs = [
            json.loads(m["content"])["tool_result"]["result"]
            for m in messages
            if m["role"] == "user" and '"tool_result"' in m["content"]
        ]
        if self.role == "policy_review":
            results = json.loads(messages[-1]["content"])["checked_rule_results"]
            output = {
                "policy_version": "0.1",
                "reviewed_rule_ids": [r["rule_id"] for r in results],
                "flagged_rule_ids": [r["rule_id"] for r in results if r["status"] == "FLAG"],
                "unknown_rule_ids": [r["rule_id"] for r in results if r["status"] == "UNKNOWN"],
            }
        else:
            from backend.app.models.review import RuleResult

            output = risk_payload([RuleResult.model_validate(r) for r in tool_outputs[-1]["rules"]])
            output["findings"] = [
                {key: value for key, value in finding.items() if key not in {"kind", "next_action"}}
                for finding in output["findings"]
            ]
        return {"content": json.dumps(output)}

    monkeypatch.setattr(AgentClient, "chat", chat)
    response = TestClient(app).post("/reviews", json=sample_request().model_dump(mode="json"))
    assert response.status_code == 200, response.text
    packet = response.json()["packet"]
    assert packet["workflow_status"] == "EXCEPTIONS_FOR_REVIEW"
    assert [run["agent"] for run in packet["agent_runs"]] == [
        "extraction",
        "policy_review",
        "risk_summary",
    ]
    assert packet["model_calls"] == 6
    assert packet["model_metadata"]["usage"]["total_tokens"] == 60
    assert {t["name"] for t in packet["agent_runs"][1]["tool_calls"]} == {
        "get_policy_rules",
        "evaluate_policy",
    }
    assert {r["rule_id"] for r in packet["risk_findings"]} == {"P03", "P04", "P06"}
