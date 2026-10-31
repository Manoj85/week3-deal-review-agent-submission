"""Meaningful API/graph tests for outcomes and evidence, not live-model quality."""
from fastapi.testclient import TestClient
import pytest
from backend.app.main import app
from backend.run_sample import sample_request

client = TestClient(app)


def run(text=None):
    request = sample_request().model_dump(mode='json')
    if text is not None:
        request['proposal_text'] = text
    response = client.post('/reviews', json=request)
    assert response.status_code == 200, response.text
    return response.json()


def statuses(packet):
    return {r['rule_id']: r['status'] for r in packet['rules']}


def test_sample_expected_packet_and_exact_evidence():
    packet = run()
    assert statuses(packet) == {'P01':'PASS','P02':'PASS','P03':'FLAG',
        'P04':'FLAG','P05':'PASS','P06':'FLAG'}
    assert packet['workflow_status'] == 'EXCEPTIONS_FOR_REVIEW'
    assert packet['terms']['requested_amount']['value'] == '120000'
    assert packet['terms']['guarantor']['value'] is None
    assert packet['terms']['applicant_contact']['value'] == 'Maya Patel'
    assert packet['model_calls'] == 0
    assert packet['human_review_required'] is True
    for fact in packet['terms'].values():
        if fact['state'] == 'KNOWN':
            assert fact['evidence']
        for evidence in fact['evidence']:
            assert packet['normalized_source'][evidence['start']:evidence['end']] == evidence['quote']
            assert evidence['document_id'] == 'SAMPLE-001'
    assert [e['step'] for e in packet['events']] == [
        'extract_terms','check_policy','route_packet','summarize_packet']


def test_changed_values_recompute_instead_of_canned_answer():
    text = sample_request().proposal_text.replace('USD 400,000','USD 480,000').replace('USD 72,000','USD 75,000')
    packet = run(text)
    assert statuses(packet)['P03'] == 'PASS'  # Exactly 25%.
    assert statuses(packet)['P04'] == 'PASS'  # Exactly 1.25.
    assert statuses(packet)['P06'] == 'FLAG'


def test_missing_payment_requires_clarification_and_keeps_other_flags():
    text = sample_request().proposal_text.replace('annual proposed debt service is USD 24,000','proposed payment is not supplied')
    packet = run(text)
    assert statuses(packet)['P04'] == 'UNKNOWN'
    assert statuses(packet)['P03'] == statuses(packet)['P06'] == 'FLAG'
    assert packet['workflow_status'] == 'NEEDS_CLARIFICATION'
    assert packet['clarification_questions']
    assert packet['terms']['proposed_annual_debt_service']['value'] is None


def test_conflicting_amounts_are_not_silently_selected():
    packet = run(sample_request().proposal_text + '\nThe business requests a USD 80,000 term loan.')
    assert packet['terms']['requested_amount']['state'] == 'CONFLICT'
    assert len(packet['terms']['requested_amount']['evidence']) == 2
    assert statuses(packet)['P01'] == statuses(packet)['P03'] == 'UNKNOWN'


def test_purpose_negation_vs_affirmative():
    assert statuses(run())['P05'] == 'PASS'
    text = sample_request().proposal_text.replace(
        'No proceeds will refinance existing debt or fund personal spending.',
        'Proceeds will refinance existing debt.')
    assert statuses(run(text))['P05'] == 'FLAG'


@pytest.mark.parametrize('old,new,rule',[
    ('USD 400,000','USD 0','P03'),
    ('USD 72,000','USD -72,000','P04'),
    ('December 31, 2025','December 31, 2024','P03'),
    ('requests a USD 120,000','requests a EUR 120,000','P01'),
])
def test_invalid_or_unsupported_evidence_does_not_pass(old,new,rule):
    assert statuses(run(sample_request().proposal_text.replace(old,new)))[rule] == 'UNKNOWN'


def test_all_pass_still_requires_human_review():
    text = sample_request().proposal_text.replace('USD 400,000','USD 480,000').replace('USD 72,000','USD 75,000')
    text = text.replace('July and August 2026 as included','July, August and September 2026 as included')
    text = text.replace('The September 2026 bank statement is explicitly missing.','')
    packet = run(text)
    assert set(statuses(packet).values()) == {'PASS'}
    assert packet['workflow_status'] == 'READY_FOR_REVIEW'
    assert packet['human_review_required'] is True


def test_conflicting_document_inclusion_requires_clarification():
    text = sample_request().proposal_text.replace('July and August 2026 as included',
        'July, August and September 2026 as included')
    assert statuses(run(text))['P06'] == 'UNKNOWN'


def test_api_rejects_malformed_requests_and_documents_contract():
    assert client.post('/reviews',json={'document_id':'x','submitted_on':'bad','proposal_text':'short'}).status_code == 422
    assert client.get('/health').json()['mode'] == 'offline_sample_parser'
    schema = client.get('/openapi.json').json()
    assert schema['paths']['/reviews']['post']['responses']['200']
