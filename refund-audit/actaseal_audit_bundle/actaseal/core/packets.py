from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from actaseal.core.canonical_json import canonical_json_hash
from actaseal.core.money import MoneyPacket
from actaseal.core.errors import (
    INVALID_PACKET,
    MISSING_ACTION_ID,
    MISSING_ACTION_TYPE,
    MISSING_ACTOR_ID,
    MISSING_ACTOR_ROLE,
    MISSING_ACTOR_SCOPE,
    MISSING_IDEMPOTENCY_KEY,
    MISSING_TENANT_ID,
    MISSING_WORKSPACE_ID,
    ActionValidationError,
    ActorValidationError,
    PacketValidationError,
)
from actaseal.core.money import MoneyPacket


def _require_text(value: object, field: str, code: str, error_type: type[PacketValidationError]) -> str:
    if value is None or not str(value).strip():
        raise error_type(code, f"{field} is required", field=field)
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


@dataclass(frozen=True)
class ActorPacket:
    actor_id: str
    actor_type: str | None
    actor_role: str
    tenant_scope: str
    workspace_scope: str
    authority_source: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _require_text(self.actor_id, "actor_id", MISSING_ACTOR_ID, ActorValidationError))
        object.__setattr__(self, "actor_role", _require_text(self.actor_role, "actor_role", MISSING_ACTOR_ROLE, ActorValidationError))
        object.__setattr__(self, "tenant_scope", _require_text(self.tenant_scope, "tenant_scope", MISSING_ACTOR_SCOPE, ActorValidationError))
        object.__setattr__(self, "workspace_scope", _require_text(self.workspace_scope, "workspace_scope", MISSING_ACTOR_SCOPE, ActorValidationError))
        object.__setattr__(self, "actor_type", _optional_text(self.actor_type))
        object.__setattr__(self, "authority_source", _optional_text(self.authority_source))

    @classmethod
    def from_raw(cls, **raw: object) -> "ActorPacket":
        return cls(
            actor_id=raw.get("actor_id"),
            actor_type=raw.get("actor_type"),
            actor_role=raw.get("actor_role"),
            tenant_scope=raw.get("tenant_scope"),
            workspace_scope=raw.get("workspace_scope"),
            authority_source=raw.get("authority_source"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "actor_role": self.actor_role,
            "tenant_scope": self.tenant_scope,
            "workspace_scope": self.workspace_scope,
            "authority_source": self.authority_source,
        }

    def canonical_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class ActionPacket:
    tenant_id: str
    workspace_id: str
    action_id: str
    action_type: str
    customer_id: str | None
    order_id: str | None
    payment_id: str | None
    money: MoneyPacket
    idempotency_key: str
    connector_target: str | None
    created_at: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _require_text(self.tenant_id, "tenant_id", MISSING_TENANT_ID, ActionValidationError))
        object.__setattr__(self, "workspace_id", _require_text(self.workspace_id, "workspace_id", MISSING_WORKSPACE_ID, ActionValidationError))
        object.__setattr__(self, "action_id", _require_text(self.action_id, "action_id", MISSING_ACTION_ID, ActionValidationError))
        object.__setattr__(self, "action_type", _require_text(self.action_type, "action_type", MISSING_ACTION_TYPE, ActionValidationError))
        object.__setattr__(self, "idempotency_key", _require_text(self.idempotency_key, "idempotency_key", MISSING_IDEMPOTENCY_KEY, ActionValidationError))
        if not isinstance(self.money, MoneyPacket):
            raise ActionValidationError(INVALID_PACKET, "money must be a MoneyPacket", field="money")
        object.__setattr__(self, "customer_id", _optional_text(self.customer_id))
        object.__setattr__(self, "order_id", _optional_text(self.order_id))
        object.__setattr__(self, "payment_id", _optional_text(self.payment_id))
        object.__setattr__(self, "connector_target", _optional_text(self.connector_target))
        object.__setattr__(self, "created_at", _optional_text(self.created_at))

    @classmethod
    def from_raw(cls, **raw: object) -> "ActionPacket":
        money = raw.get("money")
        if isinstance(money, dict):
            money = MoneyPacket.from_raw(money.get("amount"), money.get("currency"))
        return cls(
            tenant_id=raw.get("tenant_id"),
            workspace_id=raw.get("workspace_id"),
            action_id=raw.get("action_id"),
            action_type=raw.get("action_type"),
            customer_id=raw.get("customer_id"),
            order_id=raw.get("order_id"),
            payment_id=raw.get("payment_id"),
            money=money,
            idempotency_key=raw.get("idempotency_key"),
            connector_target=raw.get("connector_target"),
            created_at=raw.get("created_at"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "customer_id": self.customer_id,
            "order_id": self.order_id,
            "payment_id": self.payment_id,
            "money": self.money.to_dict(),
            "idempotency_key": self.idempotency_key,
            "connector_target": self.connector_target,
            "created_at": self.created_at,
        }

    def canonical_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class EvidencePacket:
    evidence_id: str
    claim_type: str
    source_type: str | None
    source_authority: str
    tenant_id: str
    workspace_id: str
    subject_id: str | None
    object_id: str | None
    freshness_timestamp: str | None
    issuer: str | None
    content_hash: str
    attestation: str | None = None
    money: MoneyPacket | None = None
    # ONESHOT-SEAL S1.3: the raw content content_hash claims to be a
    # digest OF. Optional (None = the historical "content_hash checked
    # for presence only" behavior, unchanged) -- a caller that supplies
    # the actual content lets verify_evidence_packet independently
    # recompute sha256(content) and detect a mismatch, rather than
    # trusting the caller-asserted hash string alone.
    content: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_text(self.evidence_id, "evidence_id", INVALID_PACKET, PacketValidationError))
        object.__setattr__(self, "claim_type", _require_text(self.claim_type, "claim_type", INVALID_PACKET, PacketValidationError))
        object.__setattr__(self, "source_authority", _require_text(self.source_authority, "source_authority", INVALID_PACKET, PacketValidationError))
        object.__setattr__(self, "tenant_id", _require_text(self.tenant_id, "tenant_id", MISSING_TENANT_ID, PacketValidationError))
        object.__setattr__(self, "workspace_id", _require_text(self.workspace_id, "workspace_id", MISSING_WORKSPACE_ID, PacketValidationError))
        object.__setattr__(self, "content_hash", _require_text(self.content_hash, "content_hash", INVALID_PACKET, PacketValidationError))
        object.__setattr__(self, "source_type", _optional_text(self.source_type))
        object.__setattr__(self, "subject_id", _optional_text(self.subject_id))
        object.__setattr__(self, "object_id", _optional_text(self.object_id))
        object.__setattr__(self, "freshness_timestamp", _optional_text(self.freshness_timestamp))
        object.__setattr__(self, "issuer", _optional_text(self.issuer))
        object.__setattr__(self, "attestation", _optional_text(self.attestation))

    @classmethod
    def from_raw(cls, **raw: object) -> "EvidencePacket":
        return cls(
            evidence_id=raw.get("evidence_id"),
            claim_type=raw.get("claim_type"),
            source_type=raw.get("source_type"),
            source_authority=raw.get("source_authority"),
            tenant_id=raw.get("tenant_id"),
            workspace_id=raw.get("workspace_id"),
            subject_id=raw.get("subject_id"),
            object_id=raw.get("object_id"),
            freshness_timestamp=raw.get("freshness_timestamp"),
            issuer=raw.get("issuer"),
            content_hash=raw.get("content_hash"),
            attestation=raw.get("attestation"),
            money=raw.get("money"),
            content=raw.get("content"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "claim_type": self.claim_type,
            "source_type": self.source_type,
            "source_authority": self.source_authority,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "subject_id": self.subject_id,
            "object_id": self.object_id,
            "freshness_timestamp": self.freshness_timestamp,
            "issuer": self.issuer,
            "content_hash": self.content_hash,
            "attestation": self.attestation,
            "money": self.money.to_dict() if self.money is not None else None,
            "content": self.content,
        }

    def canonical_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class PolicyRegistryRef:
    policy_id: str
    policy_version: str
    policy_hash: str
    policy_registry_hash: str
    compiler_version: str

    def __post_init__(self) -> None:
        for field in ("policy_id", "policy_version", "policy_hash", "policy_registry_hash", "compiler_version"):
            object.__setattr__(self, field, _require_text(getattr(self, field), field, INVALID_PACKET, PacketValidationError))

    @classmethod
    def from_raw(cls, **raw: object) -> "PolicyRegistryRef":
        return cls(
            policy_id=raw.get("policy_id"),
            policy_version=raw.get("policy_version"),
            policy_hash=raw.get("policy_hash"),
            policy_registry_hash=raw.get("policy_registry_hash"),
            compiler_version=raw.get("compiler_version"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "policy_registry_hash": self.policy_registry_hash,
            "compiler_version": self.compiler_version,
        }

    def canonical_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class ProofPacketRef:
    proof_id: str
    proof_hash: str
    proof_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "proof_id", _require_text(self.proof_id, "proof_id", INVALID_PACKET, PacketValidationError))
        object.__setattr__(self, "proof_hash", _require_text(self.proof_hash, "proof_hash", INVALID_PACKET, PacketValidationError))
        object.__setattr__(self, "proof_version", _optional_text(self.proof_version))

    @classmethod
    def from_raw(cls, **raw: object) -> "ProofPacketRef":
        return cls(
            proof_id=raw.get("proof_id"),
            proof_hash=raw.get("proof_hash"),
            proof_version=raw.get("proof_version"),
        )

    def to_dict(self) -> dict[str, object]:
        return {"proof_id": self.proof_id, "proof_hash": self.proof_hash, "proof_version": self.proof_version}

    def canonical_hash(self) -> str:
        return canonical_json_hash(self.to_dict())
