# ruff: noqa: E501  (long lines here are the report's prose, kept whole so each reads as one sentence)
"""No-integration audit (D6, ONE-SHOT 6).

A file of past agent actions and the customer's written rules go in. Every action comes out as
within authority, outside authority or cannot tell, with the rule the verdict rests on, in a
sealed pack. Nothing connects to the customer's live systems: the audit reads two files.

The rules are either a policy (the JSON the gateway itself takes) or a simple CSV with one row per
action type: action_type, currency, auto_allow_max, approval_required_above, hard_block_above,
approver_role. The actions are a CSV or JSON list with at least an action type and an amount.

How a verdict is reached, in the order it is checked:
  - the row cannot be read (no action type, amount or currency, an amount that is not a number)
        -> cannot tell: ROW_UNREADABLE
  - the rules do not name the action type, the currency is not allowed, the amount is not
    positive or is over the hard limit
        -> outside authority, whatever else the row says
  - the amount is above the automatic limit: an approval is needed
        recorded by the right role -> within; by another role -> outside; none recorded ->
        outside, or cannot tell when the file has no approval column to say
  - the amount is within the automatic limit
        the rules require evidence: within only if the file states it, otherwise cannot tell
        no evidence required -> within
A claim the file makes (an approver, an evidence claim) is what the file says; it is not checked
against any system, and the report says so.

The pack is `report.json`, `report.csv`, `report.md`, the two input files, and a seal over all of
them (the same seal `actaseal seal` writes). `verify_audit_pack` checks the seal, then recomputes the
whole report from the included inputs and compares, so a report edited and re-sealed by someone
else fails."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

from actaseal.core.decisions import ALLOW, APPROVAL_REQUIRED, BLOCK
from actaseal.core.errors import UNSUPPORTED_CURRENCY, MoneyValidationError
from actaseal.core.money import MoneyPacket
from actaseal.file_seal import SIGNATURE_DOMAIN, build_seal, verify_seal
from actaseal.policy.compiler import compile_policy
from actaseal.policy.evaluator import evaluate_action_policy
from actaseal.policy.schema import CompiledPolicy
from actaseal.reports.refund_leakage import OWED_CODES, TAX_CODES, refund_findings

_CURRENCY_CODE_LENGTH = 3
_SYMLINK_TYPE_NIBBLE = 0xA

SCHEMA = "action_audit.v1"
WITHIN_AUTHORITY = "WITHIN_AUTHORITY"
OUTSIDE_AUTHORITY = "OUTSIDE_AUTHORITY"
CANNOT_TELL = "CANNOT_TELL"
VERDICTS = (WITHIN_AUTHORITY, OUTSIDE_AUTHORITY, CANNOT_TELL)

MAX_ROWS = 50_000
MAX_BYTES = 20 * 1024 * 1024
MAX_PACK_BYTES = 200 * 1024 * 1024
MAX_PACK_MEMBERS = 20

NOTICE = (
    "This is a reading of two files, not legal advice and not a certification. The audit did not connect to "
    "any system of the customer's: an approval or an evidence claim in the actions file is what the file says, "
    "not something checked against the approver's or the evidence's own system."
)
NOT_EVALUATED = [
    "the rules' `forbidden` lists and `connector` settings (they describe the gateway's own behaviour)",
    "approvals and evidence claims against any outside system",
    "cumulative limits across actions (budgets, velocity)",
]

_COLUMNS = {
    "action_id": ("action_id", "id", "action"),
    "action_type": ("action_type", "type", "action_name"),
    "amount": ("amount", "value"),
    "currency": ("currency", "ccy"),
    "agent_id": ("agent_id", "agent", "actor", "actor_id"),
    "occurred_at": ("occurred_at", "timestamp", "date", "time"),
    "approved_by": ("approved_by", "approver"),
    "approver_role": ("approver_role", "approval_role"),
    "evidence_claims": ("evidence_claims", "evidence"),
    # Read only by the refund checks (refund_leakage.py); a row's own verdict never uses them.
    "order_id": ("order_id", "order", "order_ref"),
    "order_amount": ("order_amount", "order_value", "order_total"),
    "customer_id": ("customer_id", "customer", "customer_ref"),
    "order_date": ("order_date", "ordered_at", "order_placed_at", "delivered_at", "delivery_date"),
    "requested_at": ("requested_at", "refund_requested_at", "request_date", "return_requested_at"),
    "refund_status": ("refund_status",),
}
_ALIAS = {alias: canon for canon, aliases in _COLUMNS.items() for alias in aliases}
# "action" is ambiguous (an id in some exports, a type in others): it is only an id if there is no action_id
_ALIAS["action"] = "action_id"


class AuditError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ISO 4217 minor-unit exponents, for exports that give amounts in paise, cents or fils.
MINOR_UNIT_EXPONENT = {"INR": 2, "USD": 2, "AED": 2, "EUR": 2, "GBP": 2, "SGD": 2, "JPY": 0}
_SEPARATORS = (",", ".", " ", "'")


@dataclass(frozen=True)
class ExportShape:
    """How to read one customer's export, stated by the auditor and written into the pack.

    columns: our column name -> the export's header, ahead of the built-in names.
    action_type: the type for every row that has none (a refund export names no type).
    amount_minor_units: amounts are in the currency's minor unit (paise, cents).
    thousands_separator: a character dropped from amounts before they are read.
    skip_rows_without_amount: a row with no amount, or zero, is not a refund (an order export
    lists every order, and Shopify gives each extra item of an order a row of its own); such
    rows are left out and counted in the report.
    """

    columns: dict[str, str] = field(default_factory=dict)
    action_type: str | None = None
    amount_minor_units: bool = False
    thousands_separator: str | None = None
    skip_rows_without_amount: bool = False
    # strptime pattern of the export's dates (Razorpay writes dd/mm/yyyy hh:mm:ss); read into ISO
    # so the return-window check can use them. A date that does not match fails the audit.
    date_format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "columns": dict(sorted(self.columns.items())),
            "action_type": self.action_type,
            "amount_minor_units": self.amount_minor_units,
            "thousands_separator": self.thousands_separator,
        }
        if self.skip_rows_without_amount:
            out["skip_rows_without_amount"] = True
        if self.date_format:
            out["date_format"] = self.date_format
        return out

    @classmethod
    def from_dict(cls, raw: Any) -> ExportShape:
        if not isinstance(raw, dict):
            raise AuditError("AUDIT_BAD_SHAPE", "the export shape must be an object")
        columns = raw.get("columns") or {}
        if not isinstance(columns, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in columns.items()
        ):
            raise AuditError("AUDIT_BAD_SHAPE", "columns must map names to headers")
        return cls(
            columns=dict(columns),
            action_type=raw.get("action_type"),
            amount_minor_units=raw.get("amount_minor_units") is True,
            thousands_separator=raw.get("thousands_separator"),
            skip_rows_without_amount=raw.get("skip_rows_without_amount") is True,
            date_format=raw.get("date_format"),
        )

    def check(self, headers: set[str]) -> None:
        for name, header in self.columns.items():
            if name not in _COLUMNS:
                raise AuditError(
                    "AUDIT_BAD_SHAPE", f"{name!r} is not a column the audit reads ({', '.join(_COLUMNS)})"
                )
            if header not in headers:
                raise AuditError("AUDIT_BAD_SHAPE", f"the export has no header {header!r}")
        if self.action_type is not None and (not isinstance(self.action_type, str) or not self.action_type.strip()):
            raise AuditError("AUDIT_BAD_SHAPE", "action_type must be a non-empty name")
        if self.date_format is not None and (not isinstance(self.date_format, str) or not self.date_format.strip()):
            raise AuditError("AUDIT_BAD_SHAPE", "date_format must be a strptime pattern")
        if self.thousands_separator is not None and self.thousands_separator not in _SEPARATORS:
            raise AuditError("AUDIT_BAD_SHAPE", f"thousands_separator must be one of {_SEPARATORS}")

    def date(self, text: str) -> str:
        if not self.date_format or not text.strip():
            return text
        try:
            return datetime.strptime(text.strip(), self.date_format).isoformat()
        except ValueError as exc:
            raise AuditError(
                "AUDIT_BAD_DATE", f"{text.strip()!r} does not match the date format {self.date_format!r}"
            ) from exc

    def amount(self, text: str, currency: str) -> str:
        if self.thousands_separator and text:
            text = text.replace(self.thousands_separator, "")
        if self.amount_minor_units and text.isdigit():
            places = MINOR_UNIT_EXPONENT.get(currency.strip().upper())
            if places is None:
                return f"{text} (minor units, currency unknown)"
            quantum = Decimal(1).scaleb(-places)
            return str(Decimal(text).scaleb(-places).quantize(quantum))
        return text


# Exports whose shape is known. A file that carries every header in `signature` is read with
# that shape when the auditor names none.
SHOPIFY_ORDERS = ExportShape(
    columns={
        "action_id": "Name",
        "order_id": "Name",
        "amount": "Refunded Amount",
        "currency": "Currency",
        "order_amount": "Total",
        "order_date": "Created at",
        "customer_id": "Email",
    },
    action_type="refund",
    skip_rows_without_amount=True,
)
# Razorpay dashboard > Reports > Refunds. One row per refund, amounts in rupees, no order column
# (the payment is the unit) and no approver: the return-window and approval checks need more files.
RAZORPAY_REFUNDS = ExportShape(
    columns={
        "action_id": "id",
        "order_id": "payment_id",
        "amount": "amount",
        "currency": "currency",
        "occurred_at": "created_at",
        "customer_id": "email", "refund_status": "status",
    },
    action_type="refund",
    date_format="%d/%m/%Y %H:%M:%S",
)
EXPORT_PRESETS = {"shopify": SHOPIFY_ORDERS, "razorpay_refunds": RAZORPAY_REFUNDS}
_PRESET_SIGNATURES = {
    "shopify": {"Name", "Refunded Amount", "Financial Status", "Lineitem name"},
    "razorpay_refunds": {"id", "payment_id", "ARN", "status", "created_at", "amount"},
}


def detect_export(headers: set[str]) -> str | None:
    for name, signature in _PRESET_SIGNATURES.items():
        if signature <= headers:
            return name
    return None


# ---------------------------------------------------------------- reading the two files


def _text(data: Any, what: str) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise AuditError("AUDIT_NOT_TEXT", f"{what} must be a file's bytes")
    if len(data) > MAX_BYTES:
        raise AuditError("AUDIT_TOO_LARGE", f"{what} is over {MAX_BYTES} bytes")
    try:
        return bytes(data).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AuditError("AUDIT_NOT_TEXT", f"{what} is not UTF-8 text") from exc


def _no_amount(text: str) -> bool:
    try:
        return not text or Decimal(text) == 0
    except (ArithmeticError, ValueError):
        return False


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value)
    return str(value).strip()


def load_actions(
    data: bytes, filename: str, *, shape: ExportShape | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    """(columns present, rows). Every row has every canonical column as text, and `_row`, its 1-based number.
    A shape, when given, says how to read this export (ExportShape)."""
    text = _text(data, "the actions file")
    if not text.strip():
        raise AuditError("AUDIT_EMPTY", "the actions file is empty")
    raw_rows: list[dict[str, Any]]
    if filename.lower().endswith(".json") or text.lstrip()[:1] in "[{":
        try:
            doc = json.loads(text, parse_float=str, parse_int=str)
        except ValueError as exc:
            raise AuditError("AUDIT_BAD_JSON", "the actions file is not valid JSON") from exc
        if isinstance(doc, dict):
            doc = doc.get("actions")
        if not isinstance(doc, list) or not all(isinstance(r, dict) for r in doc):
            raise AuditError(
                "AUDIT_BAD_SHAPE", 'JSON actions must be a list of objects, or {"actions": [...]}'
            )
        raw_rows = doc
    else:
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""))
            raw_rows = [dict(r) for r in reader]
        except csv.Error as exc:
            raise AuditError("AUDIT_BAD_CSV", "the actions file is not valid CSV") from exc
    if not raw_rows:
        raise AuditError("AUDIT_NO_ROWS", "the actions file has no rows")
    if len(raw_rows) > MAX_ROWS:
        raise AuditError("AUDIT_TOO_LARGE", f"the actions file has more than {MAX_ROWS} rows")
    headers = {str(k) for r in raw_rows for k in r if k is not None}
    # our column -> the export's header; one header may feed several columns (Shopify's `Name`
    # is both the refund and the order), so this is keyed by our column, not by the header
    source: dict[str, str] = {}
    if shape is None and (preset := detect_export(headers)) is not None:
        shape = EXPORT_PRESETS[preset]
    if shape is not None:
        shape.check(headers)
        source = dict(shape.columns)
    mapped_headers = set(source.values())
    for key in sorted(headers):
        canon = _ALIAS.get(key.strip().lower())
        if canon and canon not in source and key not in mapped_headers:
            source[canon] = key
    typed = "action_type" in source or (shape is not None and shape.action_type)
    if not typed or "amount" not in source:
        found = ", ".join(sorted(headers)[:30])
        raise AuditError(
            "AUDIT_MISSING_COLUMNS",
            "the actions file needs an action_type and an amount column; it has: "
            f"{found}. Name them with an export shape (--map amount=<header>, --action-type <type>)",
        )
    rows = []
    for number, raw in enumerate(raw_rows, start=1):
        row = dict.fromkeys(_COLUMNS, "")
        for canon, key in source.items():
            row[canon] = _stringify(raw.get(key))
        row["_row"] = str(number)
        if shape is not None:
            if not row["action_type"] and shape.action_type:
                row["action_type"] = shape.action_type
            row["amount"] = shape.amount(row["amount"], row["currency"])
            row["occurred_at"] = shape.date(row["occurred_at"])
            row["order_date"] = shape.date(row["order_date"])
            if shape.skip_rows_without_amount and _no_amount(row["amount"]):
                row["_skip"] = "1"
        if not row["action_id"]:
            row["action_id"] = f"row-{number}"
        rows.append(row)
    columns = set(source) | ({"action_type"} if shape is not None and shape.action_type else set())
    return sorted(columns), rows


@dataclass
class Rules:
    policy: CompiledPolicy
    source: str
    csv_rows: dict[str, int] = field(default_factory=dict)  # action type -> row of the rules file
    # action type -> days after the order date within which a refund is allowed (simple rules only)
    refund_window_days: dict[str, int] = field(default_factory=dict)
    # action type -> days after the refund was requested (or accepted) within which it must be paid
    refund_pay_days: dict[str, int] = field(default_factory=dict)


def _dec(text: str, what: str) -> Decimal | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise AuditError("AUDIT_RULES_UNREADABLE", f"{what} is not a number: {text!r}") from exc
    if not value.is_finite() or value < 0:
        raise AuditError("AUDIT_RULES_UNREADABLE", f"{what} must be a number of zero or more")
    return value


def load_rules(data: bytes, filename: str) -> Rules:
    text = _text(data, "the rules file")
    if not text.strip():
        raise AuditError("AUDIT_RULES_UNREADABLE", "the rules file is empty")
    if filename.lower().endswith(".json") or text.lstrip()[:1] == "{":
        try:
            raw = json.loads(text)
            policy = compile_policy(raw)
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuditError(
                "AUDIT_RULES_UNREADABLE", "the rules are not a policy the gateway can compile"
            ) from exc
        except Exception as exc:  # noqa: BLE001 -- the compiler's own error types
            raise AuditError(
                "AUDIT_RULES_UNREADABLE",
                f"the rules are not a policy the gateway can compile: {exc}",
            ) from exc
        if not policy.action_policies:
            raise AuditError("AUDIT_RULES_UNREADABLE", "the rules name no action type")
        return Rules(policy, f"{policy.policy_id}@{policy.policy_version}")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        rows = [
            {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader
        ]
    except csv.Error as exc:
        raise AuditError("AUDIT_RULES_UNREADABLE", "the rules file is not valid CSV") from exc
    if not rows:
        raise AuditError("AUDIT_RULES_UNREADABLE", "the rules file has no rows")
    limit_cols = ("auto_allow_max", "approval_required_above", "hard_block_above")
    if (
        "action_type" not in rows[0]
        or "currency" not in rows[0]
        or not any(c in rows[0] for c in limit_cols)
    ):
        raise AuditError(
            "AUDIT_RULES_UNREADABLE",
            "simple rules need action_type, currency and at least one of " + ", ".join(limit_cols),
        )
    action_types: list[str] = []
    policies: dict[str, Any] = {}
    positions: dict[str, int] = {}
    windows: dict[str, int] = {}
    pays: dict[str, int] = {}
    for number, row in enumerate(rows, start=1):
        atype = row.get("action_type", "")
        if not atype:
            raise AuditError("AUDIT_RULES_UNREADABLE", f"rules row {number} has no action_type")
        if atype in policies:
            raise AuditError(
                "AUDIT_RULES_UNREADABLE", f"rules row {number} repeats action_type {atype!r}"
            )
        limits = {c: _dec(row.get(c, ""), f"rules row {number} {c}") for c in limit_cols}
        if all(v is None for v in limits.values()):
            raise AuditError("AUDIT_RULES_UNREADABLE", f"rules row {number} sets no limit at all")
        currencies = [
            c.strip().upper() for c in row["currency"].replace("|", ";").split(";") if c.strip()
        ]
        if not currencies:
            raise AuditError("AUDIT_RULES_UNREADABLE", f"rules row {number} names no currency")
        policies[atype] = {
            "money": {
                "amount_required": True,
                "currency_required": True,
                "allowed_currencies": currencies,
                "positive_required": True,
            },
            "limits": {k: (None if v is None else format(v, "f")) for k, v in limits.items()},
            "required_evidence": [],
            "forbidden": [],
            "approval": {"required_role": row.get("approver_role") or None},
            "connector": {"executed_must_be_false": True, "mutating_must_be_false": True},
        }
        action_types.append(atype)
        positions[atype] = number
        window = row.get("refund_window_days", "")
        if window:
            if not window.isdigit():
                raise AuditError(
                    "AUDIT_RULES_UNREADABLE",
                    f"rules row {number} refund_window_days is not a whole number of days",
                )
            windows[atype] = int(window)
        pay = row.get("refund_pay_within_days", "")
        if pay:
            if not pay.isdigit():
                raise AuditError(
                    "AUDIT_RULES_UNREADABLE",
                    f"rules row {number} refund_pay_within_days is not a whole number of days",
                )
            pays[atype] = int(pay)
    try:
        policy = compile_policy(
            {
                "policy_id": "simple_rules",
                "policy_version": "simple_rules.v1",
                "action_types": action_types,
                "action_policies": policies,
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise AuditError(
            "AUDIT_RULES_UNREADABLE", f"the simple rules do not compile: {exc}"
        ) from exc
    return Rules(policy, "the rules file", positions, windows, pays)


# ---------------------------------------------------------------- deciding


def _fmt(value: Any) -> str:
    return "none" if value is None else format(value, "f")


def _where(rules: Rules, atype: str) -> str:
    row = rules.csv_rows.get(atype)
    return f"rules row {row}" if row else rules.source


def _verdict(verdict: str, reason: str, rule: str, why: str) -> dict:
    return {"verdict": verdict, "reason_code": reason, "rule": rule, "explanation": why}


def _decide(row: dict[str, str], cols: set[str], rules: Rules) -> dict:  # noqa: C901, PLR0911, PLR0912
    atype, amount_text, currency = row["action_type"], row["amount"], row["currency"].upper()
    if not atype:
        return _verdict(
            CANNOT_TELL,
            "ROW_UNREADABLE",
            "the row names no action type",
            "no action_type on this row",
        )
    policy = rules.policy.action_policies.get(atype)
    if policy is None:
        return _verdict(
            OUTSIDE_AUTHORITY,
            "UNKNOWN_ACTION_TYPE",
            f"the rules do not name action type {atype!r}",
            f"{atype!r} is not an action the rules grant authority for",
        )
    if not amount_text:
        return _verdict(
            CANNOT_TELL,
            "ROW_UNREADABLE",
            f"{atype}: the row has no amount",
            "no amount on this row",
        )
    if not currency:
        return _verdict(
            CANNOT_TELL,
            "ROW_UNREADABLE",
            f"{atype}: the row has no currency",
            "no currency on this row",
        )
    try:
        money = MoneyPacket.from_raw(amount_text, currency)
    except (MoneyValidationError, InvalidOperation, ValueError, TypeError) as exc:
        code = getattr(exc, "code", None) or type(exc).__name__
        allowed = [c.upper() for c in policy.money.allowed_currencies]
        if (
            code == UNSUPPORTED_CURRENCY
            and len(currency) == _CURRENCY_CODE_LENGTH
            and currency.isalpha()
            and currency not in allowed
            and _is_number(amount_text)
        ):
            return _verdict(
                OUTSIDE_AUTHORITY,
                "CURRENCY_NOT_ALLOWED",
                f"{atype}.money.allowed_currencies = {allowed} ({_where(rules, atype)})",
                f"{currency} is not a currency the rules allow for {atype}",
            )
        return _verdict(
            CANNOT_TELL,
            "ROW_UNREADABLE",
            f"{atype}: amount {amount_text!r} {currency!r} cannot be read as money",
            f"the amount or currency on this row cannot be read ({code})",
        )
    claims = {r.claim for r in policy.required_evidence}
    authorities = {r.claim: r.authority for r in policy.required_evidence}
    action = type("Row", (), {"action_type": atype, "money": money})()
    result = evaluate_action_policy(
        action,
        None,  # type: ignore[arg-type]
        rules.policy,
        claims,
        authorities,
        True,
        attested_money=money,
    )
    where = _where(rules, atype)
    limits = policy.limits
    code = result.reason_code
    if result.verdict == BLOCK:
        rule = {
            "CURRENCY_NOT_ALLOWED": f"{atype}.money.allowed_currencies = {list(policy.money.allowed_currencies)}",
            "NON_POSITIVE_AMOUNT": f"{atype}.money.positive_required",
            "AMOUNT_ABOVE_HARD_BLOCK": f"{atype}.limits.hard_block_above = {_fmt(limits['hard_block_above'])}",
            "MALFORMED_MONEY_PACKET": f"{atype}.money.amount_required",
        }.get(code, f"{atype}: {code}")
        why = {
            "CURRENCY_NOT_ALLOWED": f"{money.currency} is not a currency the rules allow for {atype}",
            "NON_POSITIVE_AMOUNT": "the amount is not positive",
            "AMOUNT_ABOVE_HARD_BLOCK": f"{money.amount} is over the hard limit {_fmt(limits['hard_block_above'])}",
        }.get(code, code)
        return _verdict(OUTSIDE_AUTHORITY, code, f"{rule} ({where})", why)
    if result.verdict == APPROVAL_REQUIRED:
        threshold = limits["approval_required_above"]
        rule = f"{atype}.limits.approval_required_above = {_fmt(threshold)}, approver role {policy.approval.required_role or 'any'}"
        rule = f"{rule} ({where})"
        if "approved_by" not in cols and "approver_role" not in cols:
            return _verdict(
                CANNOT_TELL,
                "APPROVAL_NOT_IN_THE_FILE",
                rule,
                f"{money.amount} needs an approval and this file has no approval column to say whether there was one",
            )
        if not row["approved_by"]:
            return _verdict(
                OUTSIDE_AUTHORITY,
                "NO_APPROVAL_RECORDED",
                rule,
                f"{money.amount} is above the automatic limit and no approval is recorded",
            )
        needed = policy.approval.required_role
        if needed:
            if "approver_role" not in cols or not row["approver_role"]:
                return _verdict(
                    CANNOT_TELL,
                    "APPROVER_ROLE_NOT_IN_THE_FILE",
                    rule,
                    f"approved by {row['approved_by']}; the rule needs role {needed} and the file does not give the approver's role",
                )
            if row["approver_role"] != needed:
                return _verdict(
                    OUTSIDE_AUTHORITY,
                    "APPROVER_ROLE_MISMATCH",
                    rule,
                    f"approved by {row['approved_by']} as {row['approver_role']}; the rule needs {needed}",
                )
        return _verdict(
            WITHIN_AUTHORITY,
            "APPROVED_BY_REQUIRED_ROLE",
            rule,
            f"approved by {row['approved_by']}"
            + (f" as {needed}" if needed else "")
            + " (as the file states; not checked against any approval system)",
        )
    if result.verdict == ALLOW:
        auto = limits["auto_allow_max"]
        rule = (
            f"{atype}.limits.auto_allow_max = {_fmt(auto)} ({where})"
            if auto is not None
            else f"{atype}: named by the rules, no amount limit ({where})"
        )
        if claims:
            stated = {
                c.strip() for c in row["evidence_claims"].replace("|", ";").split(";") if c.strip()
            }
            missing = sorted(claims - stated)
            if missing:
                return _verdict(
                    CANNOT_TELL,
                    "REQUIRED_EVIDENCE_NOT_IN_THE_FILE",
                    f"{rule}; evidence required: {', '.join(sorted(claims))}",
                    f"within the amount limit, but the rule also requires {', '.join(missing)} and the file does not show it",
                )
            return _verdict(
                WITHIN_AUTHORITY,
                "WITHIN_LIMIT_EVIDENCE_STATED",
                f"{rule}; evidence required: {', '.join(sorted(claims))}",
                "within the amount limit; the required evidence is stated in the file (not verified)",
            )
        return _verdict(
            WITHIN_AUTHORITY, "POLICY_ALLOW", rule, f"{money.amount} is within the automatic limit"
        )
    return _verdict(
        CANNOT_TELL, code or "UNDECIDED", f"{atype}: {code}", "the rules gave no clear answer"
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit(
    rows: list[dict[str, str]], columns: list[str], rules: Rules, *, inputs: dict | None = None,
    credited: dict[str, Decimal] | None = None,
) -> dict:
    cols = set(columns)
    skipped = sum(1 for r in rows if r.get("_skip"))
    rows = [r for r in rows if not r.get("_skip")]
    not_evaluated = list(NOT_EVALUATED)
    if rules.refund_window_days and "occurred_at" not in cols:
        not_evaluated.append(
            "refunds after the return window: the file has no refund date to compare with the order date"
        )
    if rules.refund_pay_days and not cols & {"requested_at", "refund_status"}:
        not_evaluated.append(
            "refunds owed to customers (paid late or not paid): the file has no refund request date "
            "and no refund status"
        )
    out_rows = []
    seen: dict[str, int] = {}
    for row in rows:
        decided = _decide(row, cols, rules)
        seen[row["action_id"]] = seen.get(row["action_id"], 0) + 1
        out_rows.append(
            {
                "row": int(row["_row"]),
                "action_id": row["action_id"],
                "action_type": row["action_type"],
                "amount": row["amount"],
                "currency": row["currency"],
                "agent_id": row["agent_id"],
                "occurred_at": row["occurred_at"],
                **decided,
            }
        )
    if credited is not None and not (
        (refund_findings(rows, None, None, credited) or {}).get("credit_notes_matched_orders")
    ):
        not_evaluated.append(
            "refunds without a GST credit note: no refunded order appears in the credit notes file; "
            "check that both files use the same order reference"
        )
    counts = {v: sum(1 for r in out_rows if r["verdict"] == v) for v in VERDICTS}
    by_rule: dict[str, int] = {}
    for r in out_rows:
        key = f"{r['verdict']} | {r['rule']}"
        by_rule[key] = by_rule.get(key, 0) + 1
    return {
        "schema": SCHEMA,
        "notice": NOTICE,
        "not_evaluated": not_evaluated,
        "rules_source": rules.source,
        "columns_in_the_actions_file": sorted(cols),
        "inputs": inputs or {},
        "counts": counts,
        "total": len(out_rows),
        "duplicate_action_ids": sorted(k for k, n in seen.items() if n > 1),
        "by_rule": [{"verdict_and_rule": k, "count": n} for k, n in sorted(by_rule.items())],
        "rows": out_rows,
        **({"rows_skipped": {"count": skipped, "reason": "no refunded amount on the row"}} if skipped else {}),
        **(
            {"refund_checks": refund}
            if (refund := refund_findings(
                rows, rules.refund_window_days, rules.refund_pay_days, credited
            ))
            is not None
            else {}
        ),
    }


# ---------------------------------------------------------------- rendering


_CSV_FIELDS = (
    "row",
    "action_id",
    "action_type",
    "amount",
    "currency",
    "agent_id",
    "occurred_at",
    "verdict",
    "reason_code",
    "rule",
    "explanation",
)


def render_csv(report: dict) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in report["rows"]:
        writer.writerow({k: _csv_safe(row.get(k, "")) for k in _CSV_FIELDS})
    return buf.getvalue()


def _csv_safe(value: Any) -> Any:
    """A cell that starts like a formula is quoted as text so a spreadsheet will not run it."""
    text = str(value)
    return (
        "'" + text
        if text[:1] in ("=", "+", "-", "@", "\t", "\r") and not _is_number(text)
        else value
    )


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
    except InvalidOperation:
        return False
    return True


def render_markdown(report: dict) -> str:
    c = report["counts"]
    lines = ["# Action audit", "", *_summary_lines(report), report["notice"],
        "",
        f"Rules read from: {report['rules_source']}. Actions in the file: {report['total']}.",
        "",
        "| Verdict | Actions |",
        "|---|---|",
        f"| Within authority | {c[WITHIN_AUTHORITY]} |",
        f"| Outside authority | {c[OUTSIDE_AUTHORITY]} |",
        f"| Cannot tell | {c[CANNOT_TELL]} |",
        "",
    ]
    if skipped := report.get("rows_skipped"):
        lines += [
            f"Rows left out as not refunds: {skipped['count']} ({skipped['reason']}).",
            "",
        ]
    if report["duplicate_action_ids"]:
        lines += [
            "Action ids that appear more than once: "
            + ", ".join(report["duplicate_action_ids"][:50]),
            "",
        ]
    for verdict, title in ((OUTSIDE_AUTHORITY, "Outside authority"), (CANNOT_TELL, "Cannot tell")):
        rows = [r for r in report["rows"] if r["verdict"] == verdict]
        if not rows:
            continue
        lines += [
            f"## {title} ({len(rows)})",
            "",
            "| Row | Action | Type | Amount | Reason | Rule |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r['row']} | {_md(r['action_id'])} | {_md(r['action_type'])} | {_md(r['amount'])} {_md(r['currency'])} "
                f"| {r['reason_code']} | {_md(r['rule'])}: {_md(r['explanation'])} |"
            )
        lines.append("")
    refund = report.get("refund_checks")
    if refund is not None:
        titles = {
            "DUPLICATE_REFUND_ON_ORDER": "More than one refund on an order",
            "REFUND_EXCEEDS_ORDER": "Refunds above what the order was worth",
            "REPEAT_CLAIMANT": (
                f"Refunded to customers with {refund['threshold_repeat_claimant']} or more refunds"
            ),
            "REFUND_AFTER_WINDOW": "Refunds after the return window",
            "REFUND_PAID_LATE": "Owed to customers: paid later than the rules allow",
            "REFUND_NOT_PAID": "Owed to customers: accepted and still not paid",
            "REFUND_WITHOUT_CREDIT_NOTE": "Refunded with no GST credit note",
        }
        lines += ["## Refund checks", ""]
        if not refund["findings"]:
            lines += ["No duplicate refunds, refunds above the order value or repeat claimants in this file.", ""]
        else:
            lines += ["| Check | Money at issue |", "|---|---|"]
            for code, title in titles.items():
                if code in refund["totals"]:
                    money = ", ".join(f"{_md(cur)} {_md(amt)}" for cur, amt in refund["totals"][code].items())
                    lines.append(f"| {title} | {money} |")
            lines += ["", "| Check | Order or customer | Actions | Money at issue | Why |", "|---|---|---|---|---|"]
            for f in refund["findings"]:
                who = f.get("order_id") or f.get("customer_id")
                lines.append(
                    f"| {titles[f['code']]} | {_md(who)} | {_md(', '.join(f['action_ids'][:20]))} "
                    f"| {_md(f['currency'])} {_md(f['amount_at_issue'])} | {_md(f['why'])} |"
                )
            lines.append("")
    lines += ["## Within authority, by rule", "", "| Rule | Actions |", "|---|---|"]
    for item in report["by_rule"]:
        if item["verdict_and_rule"].startswith(WITHIN_AUTHORITY):
            lines.append(
                f"| {_md(item['verdict_and_rule'].split(' | ', 1)[1])} | {item['count']} |"
            )
    lines += ["", "## Not evaluated", ""] + [f"- {x}" for x in report["not_evaluated"]]
    return "\n".join(lines) + "\n"


def _summary_lines(report: dict) -> list[str]:
    """What a reader needs first: how many fell outside the rules and the money involved."""
    rows = report["rows"]
    noun = "refunds" if rows and all("refund" in r["action_type"].lower() for r in rows) else "actions"
    outside = [r for r in rows if r["verdict"] == OUTSIDE_AUTHORITY]
    sums: dict[str, Decimal] = {}
    for r in outside:
        with contextlib.suppress(InvalidOperation, ValueError):
            sums[r["currency"] or "?"] = sums.get(r["currency"] or "?", Decimal(0)) + Decimal(r["amount"])
    money = ", ".join(f"{cur} {amt}" for cur, amt in sorted(sums.items())) or "nothing"
    lines = ["## Summary", "", f"- {len(outside)} of {len(rows)} {noun} fell outside the rules: {money}."]
    refund = report.get("refund_checks")
    leaks = [
        f for f in (refund or {}).get("findings", []) if f["code"] not in OWED_CODES + TAX_CODES
    ]
    uncredited = [f for f in (refund or {}).get("findings", []) if f["code"] in TAX_CODES]
    owed = [f for f in (refund or {}).get("findings", []) if f["code"] in OWED_CODES]
    if leaks:
        at_issue: dict[str, Decimal] = {}
        for f in leaks:
            at_issue[f["currency"]] = at_issue.get(f["currency"], Decimal(0)) + Decimal(f["amount_at_issue"])
        found = ", ".join(f"{cur} {amt}" for cur, amt in sorted(at_issue.items()))
        lines.append(
            f"- Refund checks found {found} at issue across {len(leaks)} findings "
            "(a refund can appear in more than one finding and in the rows above)."
        )
    if owed:
        due: dict[str, Decimal] = {}
        for f in owed:
            due[f["currency"]] = due.get(f["currency"], Decimal(0)) + Decimal(f["amount_at_issue"])
        total = ", ".join(f"{cur} {amt}" for cur, amt in sorted(due.items()))
        lines.append(
            f"- Refunds owed to customers: {total} paid later than the rules allow or not yet paid, "
            f"across {len(owed)} findings."
        )
    if uncredited:
        uncredited_sums: dict[str, Decimal] = {}
        for f in uncredited:
            cur = f["currency"]
            uncredited_sums[cur] = uncredited_sums.get(cur, Decimal(0)) + Decimal(f["amount_at_issue"])
        money = ", ".join(f"{cur} {amt}" for cur, amt in sorted(uncredited_sums.items()))
        lines.append(
            f"- Refunds with no GST credit note: {money} refunded across {len(uncredited)} orders "
            "without a matching credit note (CGST Act s.34(2): declare by 30 November after the "
            "year ends)."
        )
    if c := report["counts"][CANNOT_TELL]:
        lines.append(f"- {c} {noun} could not be judged from the file.")
    return [*lines, ""]


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------- the pack

_README = (
    "Action audit pack.\n\nreport.json / report.csv / report.md   the verdict for every action and the rule it rests on\n"
    "report.pdf                               the same report laid out for a reader\n"
    "inputs/                                  the two files the audit read, unchanged\nseal.json                                a seal over every other file\n\n"
    "Check it with:  actaseal verify-audit-pack <this pack>.zip [--public-key HEX]\n"
    "That checks the seal and then recomputes the whole report from the inputs.\n" + NOTICE + "\n"
)


def _build_report(
    actions: bytes, actions_name: str, rules: bytes, rules_name: str,
    shape: ExportShape | None = None, *, credit_notes: bytes | None = None,
) -> tuple[dict, str, str]:
    columns, rows = load_actions(actions, actions_name, shape=shape)
    loaded = load_rules(rules, rules_name)
    ext_a = (
        ".json"
        if actions_name.lower().endswith(".json") or actions.lstrip()[:1] in (b"[", b"{")
        else ".csv"
    )
    ext_r = (
        ".json" if rules_name.lower().endswith(".json") or rules.lstrip()[:1] == b"{" else ".csv"
    )
    credited = None
    if credit_notes is not None:
        from actaseal.reports.credit_notes import load_credit_notes  # noqa: PLC0415

        credited = load_credit_notes(credit_notes)
    report = audit(
        rows,
        columns,
        loaded,
        inputs={
            "actions_file": f"inputs/actions{ext_a}",
            "actions_sha256": _sha(actions),
            "rules_file": f"inputs/rules{ext_r}",
            "rules_sha256": _sha(rules),
            **({"shape": shape.to_dict()} if shape is not None else {}),
        },
        credited=credited,
    )
    return report, ext_a, ext_r


def build_audit_pack(
    actions: bytes,
    actions_name: str,
    rules: bytes,
    rules_name: str,
    *,
    signer: Any,
    output_path: str | Path,
    generated_at: str,
    shape: ExportShape | None = None,
) -> Path:
    try:
        datetime.fromisoformat(generated_at)
    except ValueError as exc:
        raise AuditError("AUDIT_BAD_TIME", "generated_at must be an ISO 8601 time") from exc
    report, ext_a, ext_r = _build_report(actions, actions_name, rules, rules_name, shape)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "inputs").mkdir()
        files = {
            "report.json": json.dumps(
                dict(report, generated_at=generated_at), indent=2, sort_keys=True
            ).encode(),
            "report.csv": render_csv(report).encode(),
            "report.md": render_markdown(report).encode(),
            "report.pdf": build_audit_report_pdf(report, generated_at=generated_at),
            f"inputs/actions{ext_a}": actions,
            f"inputs/rules{ext_r}": rules,
            "README.txt": _README.encode(),
        }
        for name, data in files.items():
            (base / name).write_bytes(data)
        seal = build_seal(
            [str(base / n) for n in files], base=base, label="action audit", created_at=generated_at
        )
        seal["signature"] = _sign(seal, signer)
        files["seal.json"] = json.dumps(seal, indent=2).encode()
        out = Path(output_path)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items():
                z.writestr(name, data)
    return out


def _sign(seal: dict, signer: Any) -> dict | None:
    """The seal's own signature form (Ed25519 over the seal hash), made with the deployment's signer.
    A signer of another algorithm leaves the seal unsigned rather than in a form the seal check rejects."""
    if signer is None or getattr(signer, "algorithm", "ed25519") != "ed25519":
        return None
    digest = bytes.fromhex(seal["seal_sha256"])
    return {
        "algorithm": "ed25519",
        "key_id": signer.key_id,
        "public_key_hex": signer.public_key().hex(),
        "signature_hex": signer.sign(SIGNATURE_DOMAIN + digest).hex(),
    }


def _safe_members(z: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = z.infolist()
    if len(infos) > MAX_PACK_MEMBERS or sum(i.file_size for i in infos) > MAX_PACK_BYTES:
        raise AuditError("AUDIT_PACK_TOO_LARGE", "the pack has too many or too large members")
    for info in infos:
        p = PurePosixPath(info.filename)
        if (
            p.is_absolute()
            or ".." in p.parts
            or "\\" in info.filename
            or info.filename.startswith("/")
            or (info.external_attr >> 28) == _SYMLINK_TYPE_NIBBLE
        ):
            raise AuditError("AUDIT_PACK_UNSAFE", f"unsafe member name {info.filename!r}")
    return infos


def verify_audit_pack(path: str | Path, *, public_key_hex: str | None = None) -> dict:
    """{"verified", "failures", "warnings", "counts", "signed_by"}: the seal, then the report recomputed from the inputs."""
    result: dict[str, Any] = {
        "verified": False,
        "failures": [],
        "warnings": [],
        "counts": None,
        "signed_by": None,
    }
    failures: list[str] = result["failures"]
    try:
        with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
            infos = _safe_members(z)
            base = Path(tmp)
            for info in infos:
                if info.is_dir():
                    continue
                target = base / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info.filename))
            seal_path = base / "seal.json"
            if not seal_path.is_file():
                failures.append("SEAL_MISSING")
                return result
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            sealed = verify_seal(seal, base=base, expected_public_key_hex=public_key_hex)
            failures.extend(sealed.failures)
            result["warnings"] = list(sealed.warnings)
            result["signed_by"] = sealed.signed_by
            listed = {e.get("path") for e in seal.get("files", []) if isinstance(e, dict)}
            present = {i.filename for i in infos if not i.is_dir()} - {"seal.json"}
            for extra in sorted(present - listed):
                failures.append(f"FILE_NOT_SEALED: {extra}")
            _recompute(base, failures, result)
    except AuditError as exc:
        failures.append(f"{exc.code}: {exc}")
    except (OSError, zipfile.BadZipFile, ValueError, KeyError, TypeError, AttributeError) as exc:
        failures.append(f"PACK_UNREADABLE: {type(exc).__name__}")
    result["verified"] = not failures
    return result


def _recompute(base: Path, failures: list[str], result: dict) -> None:
    try:
        report = json.loads((base / "report.json").read_text(encoding="utf-8"))
        names = report["inputs"]
        actions = (base / names["actions_file"]).read_bytes()
        rules = (base / names["rules_file"]).read_bytes()
        shape = ExportShape.from_dict(names["shape"]) if "shape" in names else None
        fresh, _, _ = _build_report(actions, names["actions_file"], rules, names["rules_file"], shape)
    except (OSError, ValueError, KeyError, TypeError, AuditError) as exc:
        failures.append(f"RECOMPUTE_IMPOSSIBLE: {type(exc).__name__}")
        return
    claimed = {k: v for k, v in report.items() if k != "generated_at"}
    if json.dumps(claimed, sort_keys=True) != json.dumps(fresh, sort_keys=True):
        failures.append("RECOMPUTE_MISMATCH: report.json is not what these inputs and rules give")
    if (base / "report.csv").read_text(encoding="utf-8") != render_csv(fresh):
        failures.append("RECOMPUTE_MISMATCH: report.csv")
    if (base / "report.md").read_text(encoding="utf-8") != render_markdown(fresh):
        failures.append("RECOMPUTE_MISMATCH: report.md")
    pdf = base / "report.pdf"
    if pdf.is_file():
        # The PDF is a layout of report.json and is covered by the seal. Laid out again here, a
        # different fpdf2 version can give other bytes for the same report, so a difference is
        # reported, never counted as a failure: report.json, .csv and .md are the record.
        generated_at = str(report.get("generated_at", ""))
        if pdf.read_bytes() != build_audit_report_pdf(fresh, generated_at=generated_at):
            result["warnings"].append(
                "REPORT_PDF_LAYOUT_DIFFERS: report.pdf is sealed but lays out differently here"
            )
    result["counts"] = fresh["counts"]


def build_audit_report_pdf(report: dict, *, generated_at: str) -> bytes:
    """report.pdf: the report laid out for a reader (actaseal.reports.audit_report_pdf)."""
    from actaseal.reports.audit_report_pdf import build_audit_report_pdf as render  # noqa: PLC0415

    return render(report, generated_at=generated_at)


# ---------------------------------------------------------------- command line and HTTP


def run_cli(
    actions_path: str, rules_path: str, out_path: str, *, signing_key_file: str | None, key_id: str,
    shape: ExportShape | None = None,
) -> tuple[int, str]:
    """(exit code, message): 0 written, 2 refused (nothing written)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: PLC0415

    from actaseal.signing import LocalDevSigner  # noqa: PLC0415

    try:
        actions = Path(actions_path).read_bytes()
        rules = Path(rules_path).read_bytes()
        signer = None
        if signing_key_file:
            key = Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(Path(signing_key_file).read_text().strip())
            )
            signer = LocalDevSigner(key, key_id=key_id)
        build_audit_pack(
            actions,
            Path(actions_path).name,
            rules,
            Path(rules_path).name,
            signer=signer,
            output_path=out_path,
            generated_at=datetime.now(UTC).isoformat(),
            shape=shape,
        )
    except AuditError as exc:
        _remove(out_path)
        return 2, f"{exc.code}: {exc}"
    except (OSError, ValueError) as exc:
        _remove(out_path)
        return 2, f"AUDIT_FAILED: {type(exc).__name__}: {exc}"
    note = "" if signing_key_file else " (unsigned: no --signing-key-file)"
    return 0, f"wrote {out_path}{note}"


def _remove(path: str) -> None:
    with contextlib.suppress(OSError):
        Path(path).unlink()


def http_response(body: Any, signer: Any) -> Any:
    """The pack as the answer to `POST /audit/actions`."""
    from fastapi import HTTPException, Response  # noqa: PLC0415

    if (
        not isinstance(body, dict)
        or not isinstance(body.get("actions"), str)
        or not isinstance(body.get("rules"), str)
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "AUDIT_BAD_REQUEST",
                "message": "send {actions, rules} as the text of the two files",
            },
        )
    with tempfile.TemporaryDirectory() as tmp:
        try:
            out = build_audit_pack(
                body["actions"].encode("utf-8"),
                str(body.get("actions_name") or "actions.csv"),
                body["rules"].encode("utf-8"),
                str(body.get("rules_name") or "rules.json"),
                signer=signer,
                output_path=Path(tmp) / "audit.zip",
                generated_at=datetime.now(UTC).isoformat(),
            )
        except AuditError as exc:
            raise HTTPException(
                status_code=400, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        content = out.read_bytes()
        counts = verify_audit_pack(out)["counts"] or {}
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="action-audit.zip"',
            "X-Audit-Within": str(counts.get(WITHIN_AUTHORITY, 0)),
            "X-Audit-Outside": str(counts.get(OUTSIDE_AUTHORITY, 0)),
            "X-Audit-Cannot-Tell": str(counts.get(CANNOT_TELL, 0)),
        },
    )
