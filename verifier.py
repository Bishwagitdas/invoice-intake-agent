from datetime import date
from typing import Any, Dict, List, Tuple

TAX_RATES = {
    "T10": 0.10,
    "T08": 0.08,
}


# ============================================================
# SAFE DATE PARSER
# ============================================================

def _safe_date(value):
    """
    Safely parse YYYY-MM-DD date.

    Returns:
        date   -> valid date
        None   -> missing or invalid date
    """

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    try:
        return date.fromisoformat(value)

    except (ValueError, TypeError):
        return None


# ============================================================
# VERIFICATION
# ============================================================

def verify(
    invoice
) -> Tuple[bool, List[str], Dict[str, Any]]:

    errors = []
    details = {}

    # ========================================================
    # DATES
    # ========================================================

    issue = _safe_date(
        invoice.issue_date
    )

    due = _safe_date(
        invoice.due_date
    )

    if invoice.issue_date in (None, ""):
        errors.append(
            "Issue date could not be extracted."
        )

    elif issue is None:
        errors.append(
            "Invalid issue date format."
        )

    if invoice.due_date in (None, ""):
        errors.append(
            "Due date could not be extracted."
        )

    elif due is None:
        errors.append(
            "Invalid due date format."
        )

    if (
        issue is not None
        and due is not None
        and due < issue
    ):
        errors.append(
            "Due date is earlier than issue date."
        )

    # ========================================================
    # CURRENCY
    # ========================================================

    if invoice.currency != "JPY":
        errors.append(
            "Accounting API only supports JPY."
        )

    # ========================================================
    # TAX CODES
    # ========================================================

    unknown = [
        line.tax_code
        for line in invoice.lines
        if line.tax_code not in TAX_RATES
    ]

    if unknown:
        errors.append(
            f"Unknown tax code(s): "
            f"{sorted(set(unknown))}"
        )

    # ========================================================
    # SUBTOTAL
    # ========================================================

    expected_subtotal = sum(
        line.amount
        for line in invoice.lines
        if line.amount is not None
    )

    details["expected_subtotal"] = (
        expected_subtotal
    )

    if invoice.subtotal is None:
        errors.append(
            "Subtotal could not be extracted."
        )

    elif invoice.subtotal != expected_subtotal:
        errors.append(
            f"Subtotal mismatch: "
            f"extracted={invoice.subtotal}, "
            f"calculated={expected_subtotal}"
        )

    # ========================================================
    # TAX BY CODE
    # ========================================================

    by_code = {}

    for line in invoice.lines:

        if line.amount is None:
            continue

        if line.tax_code not in TAX_RATES:
            continue

        by_code[line.tax_code] = (
            by_code.get(
                line.tax_code,
                0
            )
            + line.amount
        )

    tax_by_code = {
        code: int(
            subtotal
            * TAX_RATES[code]
        )
        for code, subtotal in by_code.items()
    }

    expected_tax = sum(
        tax_by_code.values()
    )

    details["tax_by_code"] = (
        tax_by_code
    )

    details["expected_tax"] = (
        expected_tax
    )

    if invoice.tax_amount is None:

        errors.append(
            "Tax amount could not be extracted."
        )

    elif invoice.tax_amount != expected_tax:

        errors.append(
            f"Tax mismatch: "
            f"extracted={invoice.tax_amount}, "
            f"calculated={expected_tax}"
        )

    # ========================================================
    # TOTAL
    # ========================================================

    expected_total = (
        expected_subtotal
        + expected_tax
    )

    details["expected_total"] = (
        expected_total
    )

    if invoice.total_amount is None:

        errors.append(
            "Total amount could not be extracted."
        )

    elif invoice.total_amount != expected_total:

        errors.append(
            f"Total mismatch: "
            f"extracted={invoice.total_amount}, "
            f"calculated={expected_total}"
        )

    # ========================================================
    # RESULT
    # ========================================================

    return (
        len(errors) == 0,
        errors,
        details
    )