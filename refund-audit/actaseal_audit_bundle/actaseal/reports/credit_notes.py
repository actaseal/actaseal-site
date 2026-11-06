"""A credit notes file (GSTR-1 export, Tally or Shopify register), read as order -> amount credited.

Only two columns matter: the order reference and the credit note's value, whatever the export calls
them (headers are compared lower-cased, with spaces and hyphens read as underscores). Several credit
notes on one order are added up. A file without both columns, or with a value that is not a number,
is refused by name: a credit notes file read wrongly would call credited refunds uncredited.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from actaseal.reports.action_audit import MAX_BYTES, AuditError

ORDER_HEADERS = ("order_id", "order", "order_ref", "order_number", "order_no")
AMOUNT_HEADERS = (
    "amount", "credit_note_value", "credit_note_amount", "credit_amount", "note_value", "value",
    "total",
)


def _key(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _refuse(message: str) -> AuditError:
    return AuditError("AUDIT_BAD_CREDIT_NOTES", message)


def load_credit_notes(data: bytes) -> dict[str, Decimal]:
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_BYTES:
        raise _refuse(f"the credit notes file must be a file of at most {MAX_BYTES} bytes")
    try:
        text = bytes(data).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _refuse("the credit notes file is not UTF-8 text") from None
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        rows = list(reader)
        headers = {_key(h): h for h in (reader.fieldnames or []) if h}
    except csv.Error:
        raise _refuse("the credit notes file is not valid CSV") from None
    order = next((headers[h] for h in ORDER_HEADERS if h in headers), None)
    amount = next((headers[h] for h in AMOUNT_HEADERS if h in headers), None)
    if not rows or order is None or amount is None:
        found = ", ".join(sorted(headers.values())[:20]) or "none"
        raise _refuse(
            "the credit notes file needs an order reference column (e.g. Order Number) and a value "
            f"column (e.g. Credit Note Value); it has: {found}"
        )
    credited: dict[str, Decimal] = {}
    for number, row in enumerate(rows, start=2):
        ref = (row.get(order) or "").strip()
        if not ref:
            continue
        bad = f"line {number} of the credit notes file has a value that is not a number"
        try:
            value = Decimal((row.get(amount) or "").strip().replace(",", ""))
        except (InvalidOperation, ValueError):
            raise _refuse(bad) from None
        if not value.is_finite():
            raise _refuse(bad)
        credited[ref] = credited.get(ref, Decimal(0)) + value
    return credited
