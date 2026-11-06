from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from actaseal.core.canonical_json import canonical_json_hash
from actaseal.core.errors import (
    INVALID_AMOUNT,
    INVALID_MONEY_PRECISION,
    MISSING_AMOUNT,
    MISSING_CURRENCY,
    MoneyValidationError,
    NON_POSITIVE_AMOUNT,
    UNSUPPORTED_CURRENCY,
)

SUPPORTED_CURRENCIES = {"INR": 2, "USD": 2, "AED": 2}


@dataclass(frozen=True)
class MoneyPacket:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _parse_amount(self.amount))
        object.__setattr__(self, "currency", _parse_currency(self.currency))
        _validate_money(self.amount, self.currency, allow_zero=False)

    @classmethod
    def from_raw(cls, amount: object, currency: object, *, allow_zero: bool = False) -> "MoneyPacket":
        parsed_amount = _parse_amount(amount)
        parsed_currency = _parse_currency(currency)
        _validate_money(parsed_amount, parsed_currency, allow_zero=allow_zero)
        return cls._validated(parsed_amount, parsed_currency)

    @classmethod
    def _validated(cls, amount: Decimal, currency: str) -> "MoneyPacket":
        packet = object.__new__(cls)
        object.__setattr__(packet, "amount", amount)
        object.__setattr__(packet, "currency", currency)
        return packet

    def to_dict(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency}

    def canonical_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


def _parse_amount(amount: object) -> Decimal:
    if amount is None or amount == "":
        raise MoneyValidationError(MISSING_AMOUNT, "amount is required", field="amount")
    if isinstance(amount, bool) or isinstance(amount, float):
        raise MoneyValidationError(INVALID_AMOUNT, "amount must be a finite Decimal-compatible value", field="amount")
    try:
        parsed = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise MoneyValidationError(INVALID_AMOUNT, "amount must be a finite Decimal-compatible value", field="amount") from exc
    if not parsed.is_finite():
        raise MoneyValidationError(INVALID_AMOUNT, "amount must be finite", field="amount")
    return parsed


def _parse_currency(currency: object) -> str:
    if currency is None or not str(currency).strip():
        raise MoneyValidationError(MISSING_CURRENCY, "currency is required", field="currency")
    parsed = str(currency).strip().upper()
    if parsed not in SUPPORTED_CURRENCIES:
        raise MoneyValidationError(
            UNSUPPORTED_CURRENCY,
            "currency is not supported",
            field="currency",
            details={"supported": sorted(SUPPORTED_CURRENCIES)},
        )
    return parsed


def _validate_money(amount: Decimal, currency: str, *, allow_zero: bool) -> None:
    if amount < 0 or (amount == 0 and not allow_zero):
        raise MoneyValidationError(NON_POSITIVE_AMOUNT, "amount must be positive", field="amount")
    allowed_places = SUPPORTED_CURRENCIES[currency]
    decimal_places = max(0, -amount.as_tuple().exponent)
    if decimal_places > allowed_places:
        raise MoneyValidationError(
            INVALID_MONEY_PRECISION,
            "amount has too many decimal places for currency",
            field="amount",
            details={"currency": currency, "max_decimal_places": allowed_places},
        )
