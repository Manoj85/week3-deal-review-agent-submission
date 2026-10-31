"""Unit: extraction and fictional-policy checks without HTTP or graph execution."""

import pytest

from backend.app.models.review import ReviewRequest
from backend.app.services.extraction import extract
from backend.app.services.policy import evaluate
from backend.run_sample import sample_request


def run(text=None):
    request = sample_request()
    if text is not None:
        request = ReviewRequest.model_validate({**request.model_dump(), "proposal_text": text})
    terms = extract(request)
    return {
        "terms": {name: fact.model_dump() for name, fact in terms.items()},
        "rules": [rule.model_dump() for rule in evaluate(terms, request.submitted_on)],
    }


def statuses(packet):
    return {r["rule_id"]: r["status"] for r in packet["rules"]}


def test_changed_values_recompute_instead_of_canned_answer():
    text = (
        sample_request()
        .proposal_text.replace("USD 400,000", "USD 480,000")
        .replace("USD 72,000", "USD 75,000")
    )
    packet = run(text)
    assert statuses(packet)["P03"] == "PASS"  # Exactly 25%.
    assert statuses(packet)["P04"] == "PASS"  # Exactly 1.25.
    assert statuses(packet)["P06"] == "FLAG"


def test_conflicting_amounts_are_not_silently_selected():
    packet = run(sample_request().proposal_text + "\nThe business requests a USD 80,000 term loan.")
    assert packet["terms"]["requested_amount"]["state"] == "CONFLICT"
    assert len(packet["terms"]["requested_amount"]["evidence"]) == 2
    assert statuses(packet)["P01"] == statuses(packet)["P03"] == "UNKNOWN"


def test_purpose_negation_vs_affirmative():
    assert statuses(run())["P05"] == "PASS"
    text = sample_request().proposal_text.replace(
        "No proceeds will refinance existing debt or fund personal spending.",
        "Proceeds will refinance existing debt.",
    )
    assert statuses(run(text))["P05"] == "FLAG"


@pytest.mark.parametrize(
    "old,new,rule",
    [
        ("USD 400,000", "USD 0", "P03"),
        ("USD 72,000", "USD -72,000", "P04"),
        ("December 31, 2025", "December 31, 2024", "P03"),
        ("requests a USD 120,000", "requests a EUR 120,000", "P01"),
    ],
)
def test_invalid_or_unsupported_evidence_does_not_pass(old, new, rule):
    assert statuses(run(sample_request().proposal_text.replace(old, new)))[rule] == "UNKNOWN"


def test_conflicting_document_inclusion_requires_clarification():
    text = sample_request().proposal_text.replace(
        "July and August 2026 as included", "July, August and September 2026 as included"
    )
    assert statuses(run(text))["P06"] == "UNKNOWN"
