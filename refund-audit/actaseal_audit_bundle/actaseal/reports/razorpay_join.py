"""Razorpay's Refunds report joined to its Payments report, as a file the refund audit reads.

The Refunds export carries neither the order value nor the order date; the Payments export has both
(``amount``, ``created_at``) under the refund's ``payment_id``. The join fills ``order_amount`` and
``order_date`` so the audit can check refunds above the order value and after the return window.
A refund whose payment is not in the file, or is in another currency, gets blanks: the audit then
cannot tell, it does not guess. The summary says how many.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from actaseal.reports.action_audit import RAZORPAY_REFUNDS, AuditError, load_actions

PAYMENTS_HEADERS = {
    "id", "amount", "currency", "status", "order_id", "created_at", "amount_refunded",
}
OUT_COLUMNS = (
    "action_id", "action_type", "amount", "currency", "order_id", "order_amount",
    "order_date", "customer_id", "occurred_at",
)


def join_refunds_with_payments(refunds: bytes, payments: bytes) -> tuple[bytes, dict[str, Any]]:
    _, rows = load_actions(refunds, "refunds.csv", shape=RAZORPAY_REFUNDS)
    try:
        text = payments.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        paid = list(reader)
        headers = set(reader.fieldnames or [])
    except (UnicodeDecodeError, csv.Error) as exc:
        raise AuditError(
            "AUDIT_BAD_PAYMENTS_EXPORT", "the payments file is not readable CSV"
        ) from exc
    if not headers >= PAYMENTS_HEADERS:
        missing = ", ".join(sorted(PAYMENTS_HEADERS - headers))
        raise AuditError(
            "AUDIT_BAD_PAYMENTS_EXPORT",
            f"not a Razorpay Payments export (Reports, Payments, CSV): missing {missing}",
        )
    by_id = {p["id"]: p for p in paid if p.get("id")}

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=OUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    joined = 0
    for row in rows:
        payment = by_id.get(row["order_id"])
        match = payment is not None and payment.get("currency") == row["currency"]
        order_amount = payment["amount"] if match and payment else ""
        order_date = RAZORPAY_REFUNDS.date(payment["created_at"]) if match and payment else ""
        joined += 1 if match else 0
        writer.writerow(
            {
                **{k: row[k] for k in OUT_COLUMNS if k in row},
                "order_amount": order_amount,
                "order_date": order_date,
            }
        )
    summary = {"refunds": len(rows), "joined": joined, "payment_not_in_file": len(rows) - joined}
    return out.getvalue().encode("utf-8"), summary
