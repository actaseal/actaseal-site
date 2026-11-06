from __future__ import annotations

from dataclasses import dataclass, replace


UNKNOWN_EVIDENCE_CLAIM = "UNKNOWN_EVIDENCE_CLAIM"
UNKNOWN_EVIDENCE_AUTHORITY = "UNKNOWN_EVIDENCE_AUTHORITY"
EVIDENCE_AUTHORITY_MISMATCH = "EVIDENCE_AUTHORITY_MISMATCH"


@dataclass(frozen=True)
class EvidenceAuthorityError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class EvidenceClaimContract:
    claim_type: str
    required_source_authority: str


@dataclass(frozen=True)
class EvidenceAuthorityRule:
    source_authority: str
    may_satisfy_claims: tuple[str, ...]
    public_key: str | None = None
    """Ed25519 public key, hex-encoded.

    An authority with no key can never produce a valid attestation. This is how
    llm_output, agent_memory, untrusted_note and customer_claim are excluded:
    not by name, but by the absence of any way to sign.
    """


class EvidenceAuthorityRegistry:
    def __init__(
        self,
        claim_contracts: tuple[EvidenceClaimContract, ...],
        authority_rules: tuple[EvidenceAuthorityRule, ...],
    ) -> None:
        self._claim_contracts = {
            contract.claim_type: contract
            for contract in claim_contracts
        }
        self._authority_rules = {
            rule.source_authority: rule
            for rule in authority_rules
        }

    @classmethod
    def load_default(cls) -> "EvidenceAuthorityRegistry":
        claim_contracts = (
            EvidenceClaimContract("purchase_exists", "order_system"),
            EvidenceClaimContract("payment_captured", "payment_processor"),
            EvidenceClaimContract("refund_not_duplicate", "refund_ledger"),
            EvidenceClaimContract("approval_valid", "approval_system"),
            EvidenceClaimContract("customer_promise_policy_exists", "policy_registry"),
            EvidenceClaimContract("tenant_match", "tenant_registry"),
            EvidenceClaimContract("memory_source_verified", "memory_provenance"),
        )
        authority_rules = (
            EvidenceAuthorityRule("order_system", ("purchase_exists",)),
            EvidenceAuthorityRule("payment_processor", ("payment_captured",)),
            EvidenceAuthorityRule("refund_ledger", ("refund_not_duplicate",)),
            EvidenceAuthorityRule("approval_system", ("approval_valid",)),
            EvidenceAuthorityRule("policy_registry", ("customer_promise_policy_exists",)),
            EvidenceAuthorityRule("tenant_registry", ("tenant_match",)),
            EvidenceAuthorityRule("memory_provenance", ("memory_source_verified",)),
            EvidenceAuthorityRule("support_ticket_system", ()),
            EvidenceAuthorityRule("customer_email", ()),
            EvidenceAuthorityRule("customer_claim", ()),
            EvidenceAuthorityRule("agent_memory", ()),
            EvidenceAuthorityRule("llm_output", ()),
            EvidenceAuthorityRule("untrusted_note", ()),
        )
        return cls(claim_contracts, authority_rules)

    @classmethod
    def load_dev(cls):
        """Development registry: generates a keypair for every authority that
        may satisfy a claim, and returns the private keys alongside it.

        Not for production. Keys are regenerated on every call, so a packet
        signed by one process cannot be verified by another.

        Authorities that may satisfy no claims (llm_output, agent_memory,
        untrusted_note, customer_claim) get no key here either. They can never
        produce a valid attestation in any registry.
        """
        from actaseal.evidence.attestation import generate_authority_keypair

        base = cls.load_default()
        private_keys = {}
        rules = []
        for rule in base._authority_rules.values():
            if rule.may_satisfy_claims:
                private_key, public_hex = generate_authority_keypair()
                private_keys[rule.source_authority] = private_key
                rules.append(replace(rule, public_key=public_hex))
            else:
                rules.append(rule)
        registry = cls(tuple(base._claim_contracts.values()), tuple(rules))
        return registry, private_keys

    def public_key_for_authority(self, source_authority: str) -> str | None:
        rule = self._authority_rules.get(source_authority)
        return rule.public_key if rule else None

    def required_authority_for_claim(self, claim_type: str) -> str:
        self.require_claim_registered(claim_type)
        return self._claim_contracts[claim_type].required_source_authority

    def is_authority_allowed_for_claim(self, claim_type: str, source_authority: str) -> bool:
        self.require_claim_registered(claim_type)
        self.require_authority_registered(source_authority)
        return source_authority == self.required_authority_for_claim(claim_type)

    def require_claim_registered(self, claim_type: str) -> None:
        if claim_type not in self._claim_contracts:
            raise EvidenceAuthorityError(
                UNKNOWN_EVIDENCE_CLAIM,
                f"evidence claim is not registered: {claim_type}",
            )

    def require_authority_registered(self, source_authority: str) -> None:
        if source_authority not in self._authority_rules:
            raise EvidenceAuthorityError(
                UNKNOWN_EVIDENCE_AUTHORITY,
                f"evidence source authority is not registered: {source_authority}",
            )
