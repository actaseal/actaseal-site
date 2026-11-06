from __future__ import annotations

from typing import Any

INVALID_AMOUNT = "INVALID_AMOUNT"
MISSING_AMOUNT = "MISSING_AMOUNT"
MISSING_CURRENCY = "MISSING_CURRENCY"
UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
INVALID_MONEY_PRECISION = "INVALID_MONEY_PRECISION"
NON_POSITIVE_AMOUNT = "NON_POSITIVE_AMOUNT"
MISSING_ACTOR_ID = "MISSING_ACTOR_ID"
MISSING_ACTOR_ROLE = "MISSING_ACTOR_ROLE"
MISSING_ACTOR_SCOPE = "MISSING_ACTOR_SCOPE"
MISSING_ACTION_ID = "MISSING_ACTION_ID"
MISSING_ACTION_TYPE = "MISSING_ACTION_TYPE"
MISSING_TENANT_ID = "MISSING_TENANT_ID"
MISSING_WORKSPACE_ID = "MISSING_WORKSPACE_ID"
MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY"
INVALID_PACKET = "INVALID_PACKET"


class ConstitutionalValidationError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "details": self.details,
        }


class PacketValidationError(ConstitutionalValidationError):
    pass


class MoneyValidationError(PacketValidationError):
    pass


class ActorValidationError(PacketValidationError):
    pass


class ActionValidationError(PacketValidationError):
    pass
