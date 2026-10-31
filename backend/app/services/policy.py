"""Version 0.1 fictional policy. Decimal arithmetic, no model judgment."""

import calendar
import re
from datetime import date
from decimal import Decimal

from ..models.review import Fact, RuleResult, RuleStatus


def evaluate(terms: dict[str, Fact], submitted_on: date) -> list[RuleResult]:
    results: list[RuleResult] = []

    def known(*names: str) -> bool:
        return all(terms[n].state == "KNOWN" and terms[n].value is not None for n in names)

    def number(name: str) -> Decimal:
        return Decimal(terms[name].require_value())

    def add(
        rule: str,
        status: RuleStatus,
        explanation: str,
        refs: list[str],
        calculation: str | None = None,
        question: str | None = None,
    ) -> None:
        results.append(
            RuleResult(
                rule_id=rule,
                status=status,
                explanation=explanation,
                field_refs=refs,
                calculation=calculation,
                clarification=question,
            )
        )

    def unknown(rule: str, refs: list[str], question: str) -> None:
        add(
            rule,
            "UNKNOWN",
            "Required evidence is missing, conflicting, or invalid.",
            refs,
            question=question,
        )

    refs = ["requested_amount", "currency"]
    if known(*refs) and number("requested_amount") >= 0:
        value = number("requested_amount")
        add(
            "P01",
            "PASS" if 25000 <= value <= 150000 else "FLAG",
            "Requested principal must be USD 25,000 through 150,000 inclusive.",
            refs,
        )
    else:
        unknown(
            "P01",
            refs,
            "What is the requested principal in USD? Resolve conflicting amounts if present.",
        )

    refs = ["operating_months"]
    if known(*refs):
        add(
            "P02",
            "PASS" if number(refs[0]) >= 24 else "FLAG",
            "At least 24 operating months are required.",
            refs,
        )
    else:
        unknown("P02", refs, "How many months has the business operated continuously?")

    # This first parser supports calendar fiscal years only. Stale or future
    # financial periods must not pass simply because their amounts are present.
    current_year = (
        known("fiscal_year") and int(terms["fiscal_year"].require_value()) == submitted_on.year - 1
    )
    refs = ["requested_amount", "currency", "revenue", "fiscal_year"]
    if known(*refs) and current_year and number("revenue") > 0 and number("requested_amount") >= 0:
        amount, revenue = number("requested_amount"), number("revenue")
        ratio = amount / revenue
        add(
            "P03",
            "PASS" if ratio <= Decimal(".25") else "FLAG",
            "Requested principal / annual revenue must not exceed 0.25.",
            refs,
            f"{amount} / {revenue} = {ratio}",
        )
    else:
        unknown(
            "P03",
            refs,
            "Confirm USD principal and positive revenue for the latest completed calendar fiscal year.",
        )

    refs = [
        "cash_available",
        "existing_annual_debt_service",
        "proposed_annual_debt_service",
        "fiscal_year",
    ]
    if known(*refs) and current_year:
        cash, existing, proposed = (number(n) for n in refs[:3])
        if min(cash, existing, proposed) >= 0 and existing + proposed > 0:
            ratio = cash / (existing + proposed)
            add(
                "P04",
                "PASS" if ratio >= Decimal("1.25") else "FLAG",
                "Annual cash available / total annual debt service must be at least 1.25.",
                refs,
                f"{cash} / ({existing} + {proposed}) = {ratio}",
            )
        else:
            unknown(
                "P04",
                refs,
                "Provide nonnegative annual cash/debt amounts and positive total annual debt service.",
            )
    else:
        unknown(
            "P04",
            refs,
            "Confirm cash available and existing/proposed annual debt service in USD on compatible annual periods.",
        )

    refs = ["purpose_statement", "equipment_amount", "working_capital_amount", "requested_amount"]
    statement = terms["purpose_statement"]
    if (
        statement.state == "KNOWN"
        and statement.require_value() != "ELIGIBLE"
        and not statement.require_value().lower().startswith("no proceeds")
    ):
        add("P05", "FLAG", "An explicitly prohibited use of proceeds is present.", refs)
    elif known(*refs) and (
        statement.require_value() == "ELIGIBLE"
        or statement.require_value().lower().startswith("no proceeds")
    ):
        equipment, working, requested = (number(n) for n in refs[1:])
        if min(equipment, working, requested) >= 0 and equipment + working == requested:
            add(
                "P05",
                "PASS",
                "All requested proceeds are allocated to eligible equipment and operating working capital.",
                refs,
                f"{equipment} + {working} = {requested}",
            )
        else:
            unknown(
                "P05",
                refs,
                "Provide valid equipment/working-capital allocations totaling the requested principal.",
            )
    else:
        unknown(
            "P05",
            refs,
            "Clarify the full use and allocation of proceeds; resolve contradictory purpose statements.",
        )

    refs = ["included_financial_year", "included_bank_months", "missing_bank_months", "fiscal_year"]
    required_months = []
    year, month = submitted_on.year, submitted_on.month
    for _ in range(3):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        required_months.append((year, month))

    def months(name: str) -> set[tuple[int, int]]:
        fact = terms[name]
        if fact.state != "KNOWN":
            return set()
        value = fact.require_value()
        year_match = re.search(r"\b(\d{4})\b", value)
        if not year_match:
            return set()
        return {
            (int(year_match.group(1)), i)
            for i in range(1, 13)
            if re.search(r"\b" + calendar.month_name[i] + r"\b", value, re.I)
        }

    included, missing = months("included_bank_months"), months("missing_bank_months")
    if any(terms[n].state == "CONFLICT" for n in refs) or included & missing:
        unknown("P06", refs, "Resolve conflicting document-inclusion statements.")
    elif missing & set(required_months):
        add(
            "P06",
            "FLAG",
            "At least one of the latest three required monthly bank statements is explicitly missing.",
            refs,
        )
    elif (
        known("included_financial_year")
        and current_year
        and terms["included_financial_year"].value == terms["fiscal_year"].value
        and set(required_months) <= included
    ):
        add(
            "P06",
            "PASS",
            "Latest fiscal-year financials and three required bank statements are listed as included; authenticity is unverified.",
            refs,
        )
    else:
        unknown(
            "P06",
            refs,
            "Confirm latest fiscal-year financials and the latest three completed monthly bank statements are included.",
        )
    return results
