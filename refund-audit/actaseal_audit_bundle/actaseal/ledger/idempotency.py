from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from actaseal.core.canonical_json import canonical_json_hash
from actaseal.core.money import MoneyPacket
from actaseal.core.packets import ActionPacket


CLEAR = "CLEAR"
DUPLICATE = "DUPLICATE"
CONFLICT = "CONFLICT"
INVALID = "INVALID"

IDEMPOTENCY_CLEAR = "IDEMPOTENCY_CLEAR"
DUPLICATE_IDEMPOTENCY_KEY = "DUPLICATE_IDEMPOTENCY_KEY"
DUPLICATE_BUSINESS_ACTION = "DUPLICATE_BUSINESS_ACTION"
CONFLICTING_BUSINESS_ACTION = "CONFLICTING_BUSINESS_ACTION"
MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY"
IDEMPOTENCY_TENANT_MISMATCH = "IDEMPOTENCY_TENANT_MISMATCH"
IDEMPOTENCY_WORKSPACE_MISMATCH = "IDEMPOTENCY_WORKSPACE_MISMATCH"
INVALID_IDEMPOTENCY_PACKET = "INVALID_IDEMPOTENCY_PACKET"


@dataclass(frozen=True)
class IdempotencyRecord:
    tenant_id: str
    workspace_id: str
    action_type: str
    action_id: str
    customer_id: str | None
    order_id: str | None
    payment_id: str | None
    amount: str
    currency: str
    idempotency_key: str
    action_fingerprint: str
    first_seen_event_id: str
    decision: str
    created_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "action_type": self.action_type,
            "action_id": self.action_id,
            "customer_id": self.customer_id,
            "order_id": self.order_id,
            "payment_id": self.payment_id,
            "amount": self.amount,
            "currency": self.currency,
            "idempotency_key": self.idempotency_key,
            "action_fingerprint": self.action_fingerprint,
            "first_seen_event_id": self.first_seen_event_id,
            "decision": self.decision,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class IdempotencyCheckResult:
    status: str
    reason_code: str
    existing_record: IdempotencyRecord | None
    action_fingerprint: str | None
    idempotency_key: str | None
    allowed_to_continue: bool


class IdempotencyLedger:
    def __init__(self, records: Iterable[IdempotencyRecord] = ()) -> None:
        self._records: list[IdempotencyRecord] = []
        # First record per key, in arrival order: the same answer the old
        # scan over every record gave, found in constant time.
        self._by_key: dict[tuple, IdempotencyRecord] = {}
        self._by_business: dict[tuple, IdempotencyRecord] = {}
        for record in records:
            self._add(record)

    def _add(self, record: IdempotencyRecord) -> None:
        self._records.append(record)
        scope = (record.tenant_id, record.workspace_id, record.action_type)
        self._by_key.setdefault(scope + (record.idempotency_key,), record)
        self._by_business.setdefault(scope + (record.customer_id, record.order_id, record.payment_id), record)

    @classmethod
    def empty(cls) -> "IdempotencyLedger":
        return cls()

    @property
    def records(self) -> tuple[IdempotencyRecord, ...]:
        return tuple(self._records)

    def check(self, action: ActionPacket) -> IdempotencyCheckResult:
        parsed = _parse_action(action)
        if parsed is None:
            return IdempotencyCheckResult(
                status=INVALID,
                reason_code=INVALID_IDEMPOTENCY_PACKET,
                existing_record=None,
                action_fingerprint=None,
                idempotency_key=None,
                allowed_to_continue=False,
            )

        tenant_id, workspace_id, action_type, customer_id, order_id, payment_id, amount, currency, idempotency_key = parsed
        if idempotency_key is None:
            return IdempotencyCheckResult(
                status=INVALID,
                reason_code=MISSING_IDEMPOTENCY_KEY,
                existing_record=None,
                action_fingerprint=derive_action_fingerprint(action),
                idempotency_key=None,
                allowed_to_continue=False,
            )

        fingerprint = derive_action_fingerprint(action)
        scope = (tenant_id, workspace_id, action_type)
        record = self._by_key.get(scope + (idempotency_key,))
        if record is not None:
            return IdempotencyCheckResult(
                status=DUPLICATE,
                reason_code=DUPLICATE_IDEMPOTENCY_KEY,
                existing_record=record,
                action_fingerprint=fingerprint,
                idempotency_key=idempotency_key,
                allowed_to_continue=False,
            )

        record = self._by_business.get(scope + (customer_id, order_id, payment_id))
        if record is not None:
            if (record.amount, record.currency) == (amount, currency):
                return IdempotencyCheckResult(
                    status=DUPLICATE,
                    reason_code=DUPLICATE_BUSINESS_ACTION,
                    existing_record=record,
                    action_fingerprint=fingerprint,
                    idempotency_key=idempotency_key,
                    allowed_to_continue=False,
                )
            return IdempotencyCheckResult(
                status=CONFLICT,
                reason_code=CONFLICTING_BUSINESS_ACTION,
                existing_record=record,
                action_fingerprint=fingerprint,
                idempotency_key=idempotency_key,
                allowed_to_continue=False,
            )

        return IdempotencyCheckResult(
            status=CLEAR,
            reason_code=IDEMPOTENCY_CLEAR,
            existing_record=None,
            action_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            allowed_to_continue=True,
        )

    def record(self, action: ActionPacket, decision: str, event_id: str) -> IdempotencyRecord:
        parsed = _parse_action(action)
        if parsed is None:
            raise ValueError(INVALID_IDEMPOTENCY_PACKET)
        tenant_id, workspace_id, action_type, customer_id, order_id, payment_id, amount, currency, idempotency_key = parsed
        if idempotency_key is None:
            raise ValueError(MISSING_IDEMPOTENCY_KEY)
        record = IdempotencyRecord(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action_type=action_type,
            action_id=str(getattr(action, "action_id", "")),
            customer_id=customer_id,
            order_id=order_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
            action_fingerprint=derive_action_fingerprint(action),
            first_seen_event_id=str(event_id),
            decision=str(decision),
            created_at=_optional_text(getattr(action, "created_at", None)),
        )
        self._add(record)
        return record

    def check_and_record(self, action: ActionPacket, decision: str, event_id: str) -> IdempotencyCheckResult:
        result = self.check(action)
        if result.allowed_to_continue:
            self.record(action, decision, event_id)
        return result


def derive_action_fingerprint(action: ActionPacket) -> str:
    money = getattr(action, "money", None)
    return canonical_json_hash(
        {
            "tenant_id": _required_text(getattr(action, "tenant_id", None)),
            "workspace_id": _required_text(getattr(action, "workspace_id", None)),
            "action_type": _required_text(getattr(action, "action_type", None)),
            "customer_id": _optional_text(getattr(action, "customer_id", None)),
            "order_id": _optional_text(getattr(action, "order_id", None)),
            "payment_id": _optional_text(getattr(action, "payment_id", None)),
            "amount": _money_amount(money),
            "currency": _money_currency(money),
        }
    )


def _parse_action(action: ActionPacket) -> tuple[str, str, str, str | None, str | None, str | None, str, str, str | None] | None:
    try:
        tenant_id = _required_text(getattr(action, "tenant_id", None))
        workspace_id = _required_text(getattr(action, "workspace_id", None))
        action_type = _required_text(getattr(action, "action_type", None))
        money = getattr(action, "money", None)
        amount = _money_amount(money)
        currency = _money_currency(money)
    except (AttributeError, ValueError):
        return None
    return (
        tenant_id,
        workspace_id,
        action_type,
        _optional_text(getattr(action, "customer_id", None)),
        _optional_text(getattr(action, "order_id", None)),
        _optional_text(getattr(action, "payment_id", None)),
        amount,
        currency,
        _optional_text(getattr(action, "idempotency_key", None)),
    )


def _same_scope(record: IdempotencyRecord, tenant_id: str, workspace_id: str, action_type: str) -> bool:
    return (
        record.tenant_id == tenant_id
        and record.workspace_id == workspace_id
        and record.action_type == action_type
    )


def _required_text(value: object) -> str:
    parsed = _optional_text(value)
    if parsed is None:
        raise ValueError("required text is missing")
    return parsed


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _money_amount(money: object) -> str:
    if not isinstance(money, MoneyPacket):
        raise ValueError("money must be a MoneyPacket")
    return str(money.amount)


def _money_currency(money: object) -> str:
    if not isinstance(money, MoneyPacket):
        raise ValueError("money must be a MoneyPacket")
    return money.currency
