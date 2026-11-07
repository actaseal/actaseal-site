"""Draft GST credit notes for the refunds the audit found with none (REFUND_WITHOUT_CREDIT_NOTE).

One draft per order, for the amount refunded and not yet credited, split into taxable value and
GST at the order's rate: the refunds file's `gst_rate` when every refund on the order gives the
same one, else the rate the auditor names. With no rate the GST columns stay empty and the row
says so; a guessed rate would put a wrong figure into the books. These are drafts for the books
(Zoho Books, Tally) to issue, not credit notes: numbering, issue date, place of supply and the
CGST/SGST or IGST split are the books' to set. CGST Act s.34(2): declared by 30 November after
the year of the sale ends.
"""
from __future__ import annotations

import csv
import io
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

HEADERS = (
    "Draft", "Order", "Refunds", "Customer", "Refund date", "Currency", "Value incl. GST",
    "GST rate %", "Taxable value", "GST amount", "Note",
)
_PAISE = Decimal("0.01")
_MAX_RATE = Decimal(100)


def _rate(text: str) -> Decimal | None:
    text = str(text or "").strip().rstrip("%").strip()
    if not text:
        return None
    try:
        rate = Decimal(text)
    except InvalidOperation:
        rate = None
    if rate is None or not rate.is_finite() or rate < 0 or rate > _MAX_RATE:
        raise ValueError(f"GST rate must be a percentage from 0 to 100, not {text!r}")
    return rate


def draft_credit_notes(
    findings: list[dict[str, Any]], default_rate: str = ""
) -> tuple[str, dict[str, int]]:
    """(CSV text, counts). Empty text when nothing needs a credit note."""
    fallback = _rate(default_rate)
    drafts = [f for f in findings if f.get("code") == "REFUND_WITHOUT_CREDIT_NOTE"]
    if not drafts:
        return "", {"drafts": 0, "rate_missing": 0}
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADERS)
    missing = 0
    for number, f in enumerate(drafts, start=1):
        value = Decimal(f["amount_at_issue"])
        rate = _rate(f.get("gst_rate", "")) if f.get("gst_rate") else fallback
        if rate is None:
            missing += 1
            rate_s = taxable = gst = ""
            note = "GST rate needed: take it from the original invoice"
        else:
            base = (value * 100 / (100 + rate)).quantize(_PAISE, rounding=ROUND_HALF_UP)
            rate_s, taxable, gst = f"{rate.normalize():f}", str(base), str(value - base)
            note = "check against the original invoice before issuing"
        writer.writerow([
            f"DRAFT-{number:04d}", f["order_id"], " ".join(f["action_ids"]),
            f.get("customer_id", ""), f.get("refund_date", ""), f["currency"], str(value),
            rate_s, taxable, gst, note,
        ])
    return buf.getvalue(), {"drafts": len(drafts), "rate_missing": missing}
