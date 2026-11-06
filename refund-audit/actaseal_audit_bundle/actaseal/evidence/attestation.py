"""Ed25519 attestation for evidence packets.

An evidence packet names a source_authority. Without an attestation, that name
is a claim, not a proof: any caller may write "order_system" into the field.

An attestation is an Ed25519 signature over the canonical JSON of the packet,
excluding the attestation field itself. The registry holds each authority's
public key. Authorities that may satisfy no claims (llm_output, agent_memory,
untrusted_note, customer_claim) hold no key and can never produce a valid
attestation.
"""
from __future__ import annotations

from dataclasses import replace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from actaseal.core.canonical_json import canonical_json_dumps

MISSING_EVIDENCE_ATTESTATION = "MISSING_EVIDENCE_ATTESTATION"
INVALID_EVIDENCE_ATTESTATION = "INVALID_EVIDENCE_ATTESTATION"
AUTHORITY_CANNOT_ATTEST = "AUTHORITY_CANNOT_ATTEST"

ATTESTATION_FIELD = "attestation"


def attestation_payload(evidence) -> dict[str, object]:
    """The exact bytes an authority signs: the packet minus its own signature."""
    payload = dict(evidence.to_dict())
    payload.pop(ATTESTATION_FIELD, None)
    return payload


def signing_bytes(evidence) -> bytes:
    return canonical_json_dumps(attestation_payload(evidence)).encode("utf-8")


def sign_evidence(evidence, private_key: Ed25519PrivateKey) -> str:
    """Produce an attestation. Used by authorities and by test fixtures."""
    return private_key.sign(signing_bytes(evidence)).hex()


def signed_evidence(evidence, private_key: Ed25519PrivateKey):
    """Return a copy of `evidence` carrying a valid Ed25519 attestation.

    Public so demos and buyer-facing scripts can build attested evidence
    without importing from the test tree.
    """
    unsigned = replace(evidence, attestation=None)
    attestation = sign_evidence(unsigned, private_key)
    return replace(unsigned, attestation=attestation)


def verify_attestation(evidence, public_key_hex: str | None) -> str | None:
    """Return a failure code, or None if the attestation verifies."""
    if not public_key_hex:
        return AUTHORITY_CANNOT_ATTEST

    attestation = getattr(evidence, ATTESTATION_FIELD, None)
    if not str(attestation or "").strip():
        return MISSING_EVIDENCE_ATTESTATION

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(str(attestation)), signing_bytes(evidence))
    except (InvalidSignature, ValueError):
        return INVALID_EVIDENCE_ATTESTATION
    return None


def generate_authority_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Convenience for tests and for provisioning a new authority."""
    private_key = Ed25519PrivateKey.generate()
    public_hex = private_key.public_key().public_bytes_raw().hex()
    return private_key, public_hex
