from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


MISSING_POLICY_ID = "MISSING_POLICY_ID"
MISSING_POLICY_VERSION = "MISSING_POLICY_VERSION"
INVALID_POLICY_LIMIT = "INVALID_POLICY_LIMIT"
INVALID_POLICY_CURRENCY = "INVALID_POLICY_CURRENCY"
INVALID_POLICY_SCHEMA = "INVALID_POLICY_SCHEMA"
POLICY_COMPILE_FAILED = "POLICY_COMPILE_FAILED"
UNKNOWN_POLICY = "UNKNOWN_POLICY"
UNKNOWN_POLICY_VERSION = "UNKNOWN_POLICY_VERSION"


class PolicyValidationError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "details": self.details,
        }


@dataclass(frozen=True)
class MoneyRule:
    amount_required: bool
    currency_required: bool
    allowed_currencies: tuple[str, ...]
    positive_required: bool
    # "attested" (default): the amount must be signed by a payment system
    # (payment_captured evidence). "caller": the amount the caller states is
    # the one limited, for a helpdesk with nothing to sign it. Written into
    # the dict (and so the policy hash) only when not the default, so every
    # policy that does not use it keeps its hash.
    amount_source: str = "attested"

    def to_dict(self) -> dict[str, object]:
        return {
            "amount_required": self.amount_required,
            "currency_required": self.currency_required,
            "allowed_currencies": list(self.allowed_currencies),
            "positive_required": self.positive_required,
            **({"amount_source": self.amount_source} if self.amount_source != "attested" else {}),
        }


@dataclass(frozen=True)
class EvidenceRequirement:
    claim: str
    authority: str

    def to_dict(self) -> dict[str, str]:
        return {"claim": self.claim, "authority": self.authority}


@dataclass(frozen=True)
class ApprovalRule:
    required_role: str | None
    require_webauthn: bool = False
    # A human decides every time, whatever the amount (e.g. a durable memory
    # write). Emitted only when set, so every existing policy hashes the same.
    always_required: bool = False

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"required_role": self.required_role, "require_webauthn": self.require_webauthn}
        if self.always_required:
            out["always_required"] = True
        return out


@dataclass(frozen=True)
class ConnectorModeRule:
    executed_must_be_false: bool
    mutating_must_be_false: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "executed_must_be_false": self.executed_must_be_false,
            "mutating_must_be_false": self.mutating_must_be_false,
        }


@dataclass(frozen=True)
class SegmentRule:
    """Limits for a segment of customers or orders (L2-2). ``when`` holds the conditions,
    all of which must hold; the first matching segment's limits replace the defaults."""

    name: str
    when: dict[str, object]
    limits: dict[str, Decimal | None]

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "when": dict(self.when), "limits": self.limits}


@dataclass(frozen=True)
class ActionPolicy:
    policy_id: str
    policy_version: str
    action_type: str
    money: MoneyRule
    limits: dict[str, Decimal | None]
    required_evidence: tuple[EvidenceRequirement, ...]
    forbidden: tuple[str, ...]
    approval: ApprovalRule
    connector: ConnectorModeRule
    compiler_version: str
    # Written into the dict (and so the hash) only when present, so a policy without
    # segments keeps its hash.
    segments: tuple[SegmentRule, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "action_type": self.action_type,
            "money": self.money.to_dict(),
            "limits": self.limits,
            "required_evidence": [requirement.to_dict() for requirement in self.required_evidence],
            "forbidden": list(self.forbidden),
            "approval": self.approval.to_dict(),
            "connector": self.connector.to_dict(),
            "compiler_version": self.compiler_version,
            **({"segments": [s.to_dict() for s in self.segments]} if self.segments else {}),
        }


@dataclass(frozen=True)
class CompiledPolicy:
    policy_id: str
    policy_version: str
    action_policies: dict[str, ActionPolicy]
    compiler_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "action_policies": {
                action_type: policy.to_dict()
                for action_type, policy in sorted(self.action_policies.items())
            },
            "compiler_version": self.compiler_version,
        }
