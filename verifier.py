from datetime import date
from typing import Any, Dict, List, Tuple

TAX_RATES = {"T10": 0.10, "T08": 0.08}

def verify(invoice) -> Tuple[bool, List[str], Dict[str, Any]]:
    errors = []
    details = {}

    try:
        issue = date.fromisoformat(invoice.issue_date)
        due = date.fromisoformat(invoice.due_date)
        if due < issue:
            errors.append("Due date is earlier than issue date.")
    except ValueError:
        errors.append("Invalid date format.")

    if invoice.currency != "JPY":
        errors.append("Accounting API only supports JPY.")

    unknown = [x.tax_code for x in invoice.lines if x.tax_code not in TAX_RATES]
    if unknown:
        errors.append(f"Unknown tax code(s): {sorted(set(unknown))}")

    expected_subtotal = sum(x.amount for x in invoice.lines)
    details["expected_subtotal"] = expected_subtotal
    if invoice.subtotal != expected_subtotal:
        errors.append(
            f"Subtotal mismatch: extracted={invoice.subtotal}, calculated={expected_subtotal}"
        )

    by_code = {}
    for line in invoice.lines:
        by_code[line.tax_code] = by_code.get(line.tax_code, 0) + line.amount

    tax_by_code = {
        code: int(subtotal * TAX_RATES[code])
        for code, subtotal in by_code.items()
        if code in TAX_RATES
    }
    expected_tax = sum(tax_by_code.values())
    details["tax_by_code"] = tax_by_code
    details["expected_tax"] = expected_tax
    if invoice.tax_amount != expected_tax:
        errors.append(
            f"Tax mismatch: extracted={invoice.tax_amount}, calculated={expected_tax}"
        )

    expected_total = expected_subtotal + expected_tax
    details["expected_total"] = expected_total
    if invoice.total_amount != expected_total:
        errors.append(
            f"Total mismatch: extracted={invoice.total_amount}, calculated={expected_total}"
        )

    return len(errors) == 0, errors, details
