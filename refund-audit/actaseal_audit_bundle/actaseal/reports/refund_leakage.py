"""Refund checks that show only across rows of an audited file.

Three leaks, each stated with the money at issue:

- DUPLICATE_REFUND_ON_ORDER: more than one refund on the same order. The money at
  issue is every refund after the first.
- REFUND_EXCEEDS_ORDER: refunds on one order add up to more than the order was
  worth (``order_amount``). The money at issue is the excess. Compared only when
  every refund on the order is in one currency.
- REPEAT_CLAIMANT: one customer with REPEAT_CLAIMANT_THRESHOLD or more refunds in
  the file. The money at issue is everything refunded to them.
- REFUND_AFTER_WINDOW: a refund more days after the order (``order_date``) than the
  rules' ``refund_window_days`` for its action type allow. The money at issue is the
  refund. Runs only when the simple rules give a window.

They run only when the file has an ``order_id`` or ``customer_id`` column, read
rows exactly as ``action_audit.load_actions`` gives them, and decide nothing about
a row's own verdict. A row whose amount is not a number is left out of the sums.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

REPEAT_CLAIMANT_THRESHOLD = 3
CODES = (
    "DUPLICATE_REFUND_ON_ORDER",
    "REFUND_EXCEEDS_ORDER",
    "REPEAT_CLAIMANT",
    "REFUND_AFTER_WINDOW",
)


def _amount(text: str) -> Decimal | None:
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value.is_finite() else None


def _currency(row: dict[str, str]) -> str:
    return (row.get("currency") or "").strip().upper()


def _group(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        value = (row.get(key) or "").strip()
        if value and _amount(row.get("amount", "")) is not None:
            groups.setdefault(value, []).append(row)
    return groups


def _single_currency(rows: list[dict[str, str]]) -> str | None:
    currencies = {_currency(r) for r in rows}
    return currencies.pop() if len(currencies) == 1 else None


def _day(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _late_refunds(rows: list[dict[str, str]], window_days: dict[str, int]) -> list[dict[str, Any]]:
    late = []
    for row in rows:
        days = window_days.get(row.get("action_type", ""))
        ordered, refunded = _day(row.get("order_date", "")), _day(row.get("occurred_at", ""))
        amount = _amount(row.get("amount", ""))
        if days is None or ordered is None or refunded is None or amount is None:
            continue
        if (refunded - ordered).days > days:
            late.append({
                "code": "REFUND_AFTER_WINDOW", "order_id": (row.get("order_id") or "").strip(),
                "action_ids": [row["action_id"]], "amount_at_issue": str(amount),
                "currency": _currency(row),
                "why": f"refunded {(refunded - ordered).days} days after the order; "
                f"the window is {days} days",
            })
    return late


def refund_findings(
    rows: list[dict[str, str]], window_days: dict[str, int] | None = None
) -> dict[str, Any] | None:
    has_order = any((r.get("order_id") or "").strip() for r in rows)
    has_customer = any((r.get("customer_id") or "").strip() for r in rows)
    if not has_order and not has_customer:
        return None

    findings: list[dict[str, Any]] = []
    for order_id, group in sorted(_group(rows, "order_id").items()):
        currency = _single_currency(group)
        amounts = [_amount(r["amount"]) or Decimal(0) for r in group]
        ids = [r["action_id"] for r in group]
        if len(group) > 1 and currency is not None:
            findings.append({
                "code": "DUPLICATE_REFUND_ON_ORDER", "order_id": order_id, "action_ids": ids,
                "amount_at_issue": str(sum(amounts[1:], Decimal(0))), "currency": currency,
                "why": f"{len(group)} refunds on one order; each after the first is at issue",
            })
        order_amounts = {_amount(r.get("order_amount", "")) for r in group} - {None}
        if currency is not None and len(order_amounts) == 1:
            order_amount = order_amounts.pop()
            refunded = sum(amounts, Decimal(0))
            if order_amount is not None and refunded > order_amount:
                findings.append({
                    "code": "REFUND_EXCEEDS_ORDER", "order_id": order_id, "action_ids": ids,
                    "amount_at_issue": str(refunded - order_amount), "currency": currency,
                    "why": f"{refunded} refunded on an order worth {order_amount}",
                })
    for customer_id, group in sorted(_group(rows, "customer_id").items()):
        currency = _single_currency(group)
        if len(group) >= REPEAT_CLAIMANT_THRESHOLD and currency is not None:
            refunded = sum((_amount(r["amount"]) or Decimal(0) for r in group), Decimal(0))
            findings.append({
                "code": "REPEAT_CLAIMANT", "customer_id": customer_id,
                "action_ids": [r["action_id"] for r in group], "count": len(group),
                "amount_at_issue": str(refunded), "currency": currency,
                "why": f"{len(group)} refunds to one customer "
                f"(flagged at {REPEAT_CLAIMANT_THRESHOLD} or more)",
            })

    findings.extend(_late_refunds(rows, window_days or {}))

    totals: dict[str, dict[str, str]] = {}
    for code in CODES:
        sums: dict[str, Decimal] = {}
        for f in findings:
            if f["code"] == code:
                at_issue = Decimal(f["amount_at_issue"])
                sums[f["currency"]] = sums.get(f["currency"], Decimal(0)) + at_issue
        if sums:
            totals[code] = {c: str(a) for c, a in sorted(sums.items())}
    return {
        "threshold_repeat_claimant": REPEAT_CLAIMANT_THRESHOLD,
        "findings": findings,
        "totals": totals,
    }
