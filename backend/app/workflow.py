"""Actual LangGraph flow; nodes are offline functions at this checkpoint."""
from hashlib import sha256
from time import perf_counter
from typing import TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from .schemas import ReviewRequest, ReviewPacket, Fact, RuleResult, StepEvent
from .extraction import extract
from .policy import evaluate


class ReviewState(TypedDict, total=False):
    request: ReviewRequest
    terms: dict[str, Fact]
    rules: list[RuleResult]
    events: list[StepEvent]
    workflow_status: str
    summary: str


def extraction_step(state: ReviewState):
    return {'terms': extract(state['request']), 'events': [StepEvent(step='extract_terms')]}


def policy_step(state: ReviewState):
    return {'rules': evaluate(state['terms'], state['request'].submitted_on),
        'events': state['events'] + [StepEvent(step='check_policy')]}


def route(state: ReviewState):
    if any(r.status == 'UNKNOWN' for r in state['rules']):
        return 'clarification'
    if any(r.status == 'FLAG' for r in state['rules']):
        return 'exceptions'
    return 'ready'


def routing_step(status):
    def apply(state):
        return {'workflow_status': status,
            'events': state['events'] + [StepEvent(step='route_packet')]}
    return apply


def summary_step(state: ReviewState):
    flagged = [r.rule_id for r in state['rules'] if r.status == 'FLAG']
    unknown = [r.rule_id for r in state['rules'] if r.status == 'UNKNOWN']
    business = state['terms']['business_name'].value or 'The applicant'
    # A deterministic summary proves the packet contract without inventing prose.
    summary = (f'{business}: {len(flagged)} policy exceptions'
        f' ({", ".join(flagged) or "none"}); {len(unknown)} rules need clarification'
        f' ({", ".join(unknown) or "none"}). Human review is required. '
        'This packet does not approve or deny a loan.')
    return {'summary': summary,
        'events': state['events'] + [StepEvent(step='summarize_packet')]}


builder = StateGraph(ReviewState)
builder.add_node('extract', extraction_step)
builder.add_node('policy', policy_step)
builder.add_node('clarification', routing_step('NEEDS_CLARIFICATION'))
builder.add_node('exceptions', routing_step('EXCEPTIONS_FOR_REVIEW'))
builder.add_node('ready', routing_step('READY_FOR_REVIEW'))
builder.add_node('summary', summary_step)
builder.add_edge(START, 'extract')
builder.add_edge('extract', 'policy')
builder.add_conditional_edges('policy', route,
    {'clarification': 'clarification', 'exceptions': 'exceptions', 'ready': 'ready'})
for node in ['clarification', 'exceptions', 'ready']:
    builder.add_edge(node, 'summary')
builder.add_edge('summary', END)
graph = builder.compile()


def review(request: ReviewRequest) -> ReviewPacket:
    started = perf_counter()
    result = graph.invoke({'request': request})
    return ReviewPacket(run_id=str(uuid4()), document_id=request.document_id,
        submitted_on=request.submitted_on, normalized_source=request.proposal_text,
        source_sha256=sha256(request.proposal_text.encode()).hexdigest(),
        terms=result['terms'], rules=result['rules'], workflow_status=result['workflow_status'],
        summary=result['summary'], events=result['events'],
        clarification_questions=[r.clarification for r in result['rules'] if r.clarification],
        next_actions=[r.clarification or f'Human reviewer: consider {r.rule_id}. {r.explanation}'
            for r in result['rules'] if r.status != 'PASS'] + ['Have a human credit reviewer review the packet.'],
        elapsed_ms=round((perf_counter()-started)*1000, 3),
        limitations=['Offline sample-format parser, not a live AI agent.',
            'No arbitrary prose, PDF ingestion, persistence, human resume, or model calls yet.',
            'Document inclusion is proposal-reported; attachments are not verified.',
            'Calendar fiscal years only; unusual wording may be missed. Do not use for real lending.'])
