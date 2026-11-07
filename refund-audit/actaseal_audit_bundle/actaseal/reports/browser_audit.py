"""The refund audit as one call for the browser page (web/refund_audit_sandbox.html).

The page runs this module's real Python in the visitor's tab (Pyodide); nothing is uploaded.
Bytes in, a plain JSON-able dict out. It never raises, so the page can always show a reason, and
anything it cannot read is refused by name, never audited as if it were empty.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from actaseal.reports.action_audit import (
    AuditError,
    _build_report,
    _summary_lines,
    load_actions,
    render_csv,
    render_markdown,
)
from actaseal.reports.credit_note_draft import draft_credit_notes
from actaseal.reports.credit_notes import load_credit_notes  # noqa: F401 -- bundled for the page
from actaseal.reports.razorpay_join import join_refunds_with_payments

_CURRENCY_LEN = 3
_RULE_HEADERS = (
    "action_type", "currency", "auto_allow_max", "approval_required_above",
    "hard_block_above", "approver_role", "refund_window_days", "refund_pay_within_days",
)


def _amount(name: str, text: str) -> str:
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be zero or more")
    return str(text).strip()


def rules_from_fields(
    *, currency: str, auto_allow_max: str, approval_required_above: str, hard_block_above: str,
    approver_role: str, refund_window_days: str, refund_pay_within_days: str = "",
) -> bytes:
    """The one-row refund rules file the audit reads; a bad form field is refused."""
    cur = str(currency).strip().upper()
    if len(cur) != _CURRENCY_LEN or not cur.isalpha():
        raise ValueError("currency must be a 3-letter code")
    role = str(approver_role).strip()
    if any(c in role for c in ',"\r\n'):
        raise ValueError("approver_role must not contain commas, quotes or line breaks")
    days = str(refund_window_days).strip()
    if days and not days.isdigit():
        raise ValueError("refund_window_days must be a whole number of days")
    pay = str(refund_pay_within_days).strip()
    if pay and not pay.isdigit():
        raise ValueError("refund_pay_within_days must be a whole number of days")
    row = [
        "refund", cur, _amount("auto_allow_max", auto_allow_max),
        _amount("approval_required_above", approval_required_above),
        _amount("hard_block_above", hard_block_above), role, days, pay,
    ]
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_RULE_HEADERS)
    writer.writerow(row)
    return buf.getvalue().encode()


def run_browser_audit(
    actions: bytes, actions_name: str, rules: bytes, rules_name: str, payments: bytes | None = None,
    *, credit_notes: bytes | None = None, gst_rate: str = "",
) -> dict[str, Any]:
    try:
        draft_credit_notes([], default_rate=gst_rate)
    except ValueError as exc:
        return {"ok": False, "code": "AUDIT_BAD_RULE", "message": str(exc)}
    try:
        joined = None
        if payments is not None:
            actions, joined = join_refunds_with_payments(actions, payments)
            actions_name = "refunds_with_orders.csv"
        report, _ext_a, _ext_r = _build_report(
            actions, actions_name, rules, rules_name, credit_notes=credit_notes
        )
        findings = (report.get("refund_checks") or {}).get("findings", [])
        drafts, _counts = draft_credit_notes(findings, default_rate=gst_rate)
        return {
            "ok": True,
            "report": report,
            "summary_lines": _summary_lines(report),
            "markdown": render_markdown(report),
            "csv": render_csv(report),
            "joined": joined,
            "credit_note_drafts": drafts,
        }
    except AuditError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- the page must always get a reason
        return {"ok": False, "code": "AUDIT_FAILED", "message": f"{type(exc).__name__}: {exc}"}


def currencies_in(actions: bytes, actions_name: str) -> dict[str, Any]:
    """The currencies and approver roles a file's rows carry, so the page offers real choices."""
    try:
        _columns, rows = load_actions(actions, actions_name)
    except AuditError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- the page must always get a reason
        return {"ok": False, "code": "AUDIT_FAILED", "message": f"{type(exc).__name__}: {exc}"}
    found = {
        r["currency"].strip().upper() for r in rows if not r.get("_skip") and r["currency"].strip()
    }
    kept = [r for r in rows if not r.get("_skip")]
    roles = {r["approver_role"].strip() for r in kept if r["approver_role"].strip()}
    return {"ok": True, "currencies": sorted(found), "approver_roles": sorted(roles)}
