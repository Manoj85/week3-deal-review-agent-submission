"""Mock provider responses: no credentials, inference, or credit consumption."""

import json

import httpx
import pytest

from backend.app.services.extraction import extract
from backend.app.services.nebius import ProviderError, extract_nebius, validate_output
from backend.run_sample import sample_request


def payload():
    fields = {
        name: {"value": fact.value, "state": fact.state, "quotes": [e.quote for e in fact.evidence]}
        for name, fact in extract(sample_request()).items()
    }
    fields["purpose_statement"]["value"] = "ELIGIBLE"
    return {"fields": fields}


def test_exact_evidence_and_numeric_validation():
    request = sample_request()
    facts = validate_output(payload(), request)
    for fact in facts.values():
        for evidence in fact.evidence:
            assert request.proposal_text[evidence.start : evidence.end] == evidence.quote
    bad = payload()
    bad["fields"]["requested_amount"]["value"] = "999999"
    with pytest.raises(ValueError):
        validate_output(bad, request)
    bad = payload()
    bad["fields"]["requested_amount"]["quotes"] = ["This sentence is not in the proposal."]
    with pytest.raises(ValueError):
        validate_output(bad, request)


def test_invalid_output_gets_one_repair_attempt(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-only-key")
    monkeypatch.setenv("NEBIUS_CHAT_MODEL", "test-model")
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    calls = []

    def post(self, url, **kwargs):
        calls.append(url)
        content = "{}" if len(calls) == 1 else json.dumps(payload())
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "usage": {"total_tokens": 10},
                "model": "test-model",
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    facts, metadata = extract_nebius(sample_request())
    assert facts["requested_amount"].value == "120000"
    assert metadata["model_calls"] == 2
    assert metadata["usage"]["total_tokens"] == 20
    assert len(calls) == 2


def test_auth_failure_is_not_retried_or_exposed(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-only-key")
    monkeypatch.setenv("NEBIUS_CHAT_MODEL", "test-model")
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    calls = []

    def post(self, url, **kwargs):
        calls.append(url)
        return httpx.Response(401, text="do not expose this body")

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(ProviderError, match="HTTP 401") as error:
        extract_nebius(sample_request())
    assert "do not expose" not in str(error.value)
    assert len(calls) == 1


def test_api_provider_failure_does_not_fall_back(monkeypatch):
    from fastapi.testclient import TestClient

    import backend.app.workflows.review as workflow
    from backend.app.main import app

    monkeypatch.setenv("EXTRACTION_MODE", "nebius")

    def fail(request):
        raise ProviderError("Test provider unavailable.")

    monkeypatch.setattr(workflow, "extract_nebius", fail)
    response = TestClient(app).post("/reviews", json=sample_request().model_dump(mode="json"))
    assert response.status_code == 502
    assert response.json()["detail"] == "Test provider unavailable."
