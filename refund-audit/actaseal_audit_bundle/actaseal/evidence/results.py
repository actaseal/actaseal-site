from __future__ import annotations

from dataclasses import dataclass

from actaseal.core.money import MoneyPacket


PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class EvidenceVerificationResult:
    status: str
    evidence_id: str
    claim_type: str
    source_authority: str
    failure_codes: tuple[str, ...]
    satisfied_claims: set[str]
    money: MoneyPacket | None = None

    def to_failure_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "claim_type": self.claim_type,
            "source_authority": self.source_authority,
            "failure_codes": list(self.failure_codes),
        }


@dataclass(frozen=True)
class EvidenceSetVerificationResult:
    status: str
    satisfied_claims: set[str]
    claim_authorities: dict[str, str]
    missing_claims: set[str]
    invalid_evidence_ids: list[str]
    failures: list[dict]
    claim_money: dict[str, MoneyPacket]

    def to_policy_inputs(self) -> tuple[set[str], dict[str, str]]:
        return set(self.satisfied_claims), dict(self.claim_authorities)

    def attested_money(self) -> MoneyPacket | None:
        """The money value attested across satisfied claims, or None if
        no claim attests money, or if attesting claims disagree."""
        values = list(self.claim_money.values())
        if not values:
            return None
        first = values[0]
        for value in values[1:]:
            if value != first:
                return None
        return first
