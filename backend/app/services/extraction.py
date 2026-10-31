"""A deliberately narrow, auditable parser for the sample's explicit grammar.

This establishes an evidence contract before adding model extraction. It is not
claimed to understand arbitrary proposals or fresh paraphrases.
"""

import re

from ..models.review import Evidence, Fact, ReviewRequest

MONEY = r"(-?\d[\d,]*(?:\.\d+)?)"


def extract(request: ReviewRequest) -> dict[str, Fact]:
    text = request.proposal_text

    def capture(pattern: str, convert=lambda m: m.group(1)) -> Fact:
        evidence, values = [], []
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Offsets are half-open Python character indices into normalized_source.
            headings = list(re.finditer(r"^## (.+)$", text[: match.start()], re.MULTILINE))
            evidence.append(
                Evidence(
                    document_id=request.document_id,
                    section=headings[-1].group(1) if headings else "Proposal",
                    quote=match.group(),
                    start=match.start(),
                    end=match.end(),
                )
            )
            values.append(convert(match))
        unique = set(values)
        if not unique:
            return Fact()
        if len(unique) > 1:
            return Fact(state="CONFLICT", evidence=evidence)
        return Fact(value=values[0], state="KNOWN", evidence=evidence)

    def amount(match: re.Match[str]) -> str:
        return match.group(1).replace(",", "")

    facts = {
        "business_name": capture(
            r"([^\n.]+?) has operated continuously for \d+ months", lambda m: m.group(1).strip()
        ),
        "requested_amount": capture(r"requests a USD " + MONEY + r" term loan", amount),
        "currency": capture(r"requests a (USD) " + MONEY + r" term loan"),
        "operating_months": capture(r"has operated continuously for (\d+) months"),
        "fiscal_year": capture(r"completed fiscal year ending December 31, (\d{4})"),
        "revenue": capture(r"revenue was USD " + MONEY, amount),
        "cash_available": capture(r"cash available for debt service was USD " + MONEY, amount),
        "existing_annual_debt_service": capture(
            r"annual existing debt service is USD " + MONEY, amount
        ),
        "proposed_annual_debt_service": capture(
            r"annual proposed debt service is USD " + MONEY, amount
        ),
        "equipment_amount": capture(r"USD " + MONEY + r" will purchase a commercial oven", amount),
        "working_capital_amount": capture(
            r"USD " + MONEY + r" will fund operating working capital", amount
        ),
        "purpose_statement": capture(
            r"(No proceeds will refinance existing debt or fund personal spending|Proceeds will refinance existing debt|Proceeds will fund personal spending|Proceeds will fund speculative investment)\."
        ),
        "applicant_contact": capture(r"([A-Z][a-z]+ [A-Z][a-z]+), owner, is the applicant contact"),
        "preparer": capture(
            r"([A-Z][a-z]+ [A-Z][a-z]+), external accountant, prepared this proposal"
        ),
        "guarantor": capture(r"([A-Z][a-z]+ [A-Z][a-z]+) is explicitly named as guarantor"),
        "included_financial_year": capture(
            r"packet lists fiscal-year (\d{4}) financial statements"
        ),
        "included_bank_months": capture(
            r"monthly business bank statements for ([A-Za-z, ]+ \d{4}) as included"
        ),
        "missing_bank_months": capture(
            r"The ([A-Za-z]+ \d{4}) bank statement is explicitly missing"
        ),
    }
    return facts
