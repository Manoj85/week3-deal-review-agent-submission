"""The LLM cannot overwrite rule outcomes or invent uncited risk findings."""

import json

import httpx
import pytest

from backend.app.agents.policy_review import PolicyAssessment, validate_assessment
from backend.app.agents.risk_summary import RiskReview, validate_risks
from backend.app.services.agent_client import AgentClient, call_tool_round
from backend.app.services.nebius import ProviderError
from backend.tests.helpers import risk_payload, rules_and_terms


def test_policy_agent_cannot_hide_flags_or_skip_rules():
    _, rules = rules_and_terms()
    output = PolicyAssessment(
        policy_version="0.1",
        reviewed_rule_ids=[r.rule_id for r in rules],
        flagged_rule_ids=[],
        unknown_rule_ids=[],
    )
    with pytest.raises(ValueError, match="rule IDs"):
        validate_assessment(output, rules)
    output.flagged_rule_ids = ["P03", "P04", "P06"]
    output.reviewed_rule_ids = ["P01"]
    with pytest.raises(ValueError, match="coverage"):
        validate_assessment(output, rules)


@pytest.mark.parametrize("change", ["omit", "wrong_ref", "invent_number", "decision", "wrong_kind"])
def test_risk_guard_rejects_invalid_reviews(change):
    terms, rules = rules_and_terms()
    data = risk_payload(rules)
    if change == "omit":
        data["findings"].pop()
    if change == "wrong_ref":
        data["findings"][0]["field_refs"] = ["guarantor"]
    if change == "invent_number":
        data["summary"] = "The loan lasts 99 years."
    if change == "decision":
        data["summary"] = "The loan is approved."
    if change == "wrong_kind":
        data["findings"][0]["kind"] = "data_gap"
    with pytest.raises(ValueError):
        validate_risks(RiskReview.model_validate(data), terms, rules)


def test_agent_call_budget_is_enforced(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-only-key")
    monkeypatch.setenv("NEBIUS_CHAT_MODEL", "test-model")
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        ),
    )
    with AgentClient("test_role", "test-v1", max_calls=1) as client:
        client.chat([])
        with pytest.raises(ProviderError, match="budget"):
            client.chat([])


def test_invalid_tool_arguments_are_not_executed(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-only-key")
    monkeypatch.setenv("NEBIUS_CHAT_MODEL", "test-model")
    executed = []
    monkeypatch.setattr(
        AgentClient,
        "chat",
        lambda *args, **kwargs: {
            "content": json.dumps({"tool": "evaluate_policy", "arguments": {"threshold": 0}})
        },
    )
    with AgentClient("policy_review", "test") as client:
        with pytest.raises(ProviderError, match="invalid tool"):
            call_tool_round(client, [], {"evaluate_policy": lambda: executed.append(True)}, [])
    assert executed == []
