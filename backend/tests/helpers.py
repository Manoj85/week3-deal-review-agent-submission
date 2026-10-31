"""Shared synthetic fixtures for offline policy and API tests."""

from backend.app.services.extraction import extract
from backend.app.services.policy import evaluate
from backend.run_sample import sample_request


def rules_and_terms():
    request = sample_request()
    terms = extract(request)
    return terms, evaluate(terms, request.submitted_on)


def risk_payload(rules):
    return {
        "summary": "The financial exceptions and document gap require human review.",
        "findings": [
            {
                "rule_id": r.rule_id,
                "kind": "policy_exception" if r.status == "FLAG" else "data_gap",
                "explanation": r.explanation,
                "field_refs": r.field_refs,
                "next_action": "REVIEW_POLICY_EXCEPTION"
                if r.status == "FLAG"
                else "REQUEST_CLARIFICATION",
            }
            for r in rules
            if r.status != "PASS"
        ],
    }
