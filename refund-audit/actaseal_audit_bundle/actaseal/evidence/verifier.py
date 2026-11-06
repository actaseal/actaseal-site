from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from actaseal.core.money import MoneyPacket
from actaseal.core.packets import EvidencePacket
from actaseal.evidence.attestation import verify_attestation
from actaseal.evidence.authority import (
    EVIDENCE_AUTHORITY_MISMATCH,
    UNKNOWN_EVIDENCE_AUTHORITY,
    UNKNOWN_EVIDENCE_CLAIM,
    EvidenceAuthorityError,
    EvidenceAuthorityRegistry,
)
from actaseal.evidence.results import FAIL, PASS, EvidenceSetVerificationResult, EvidenceVerificationResult


EVIDENCE_TENANT_MISMATCH = "EVIDENCE_TENANT_MISMATCH"
EVIDENCE_WORKSPACE_MISMATCH = "EVIDENCE_WORKSPACE_MISMATCH"
MISSING_EVIDENCE_HASH = "MISSING_EVIDENCE_HASH"
MISSING_EVIDENCE_ISSUER = "MISSING_EVIDENCE_ISSUER"
MISSING_EVIDENCE_FRESHNESS = "MISSING_EVIDENCE_FRESHNESS"
INVALID_EVIDENCE_TIMESTAMP = "INVALID_EVIDENCE_TIMESTAMP"
STALE_EVIDENCE = "STALE_EVIDENCE"
FUTURE_EVIDENCE_TIMESTAMP = "FUTURE_EVIDENCE_TIMESTAMP"
DUPLICATE_EVIDENCE_ID = "DUPLICATE_EVIDENCE_ID"
REQUIRED_EVIDENCE_MISSING = "REQUIRED_EVIDENCE_MISSING"
# ONESHOT-SEAL S1.3 (superseded by C3, 2026-08-06): content_hash is now
# ALWAYS checked against actual content, not just presence. The
# original S1.3 version made this opt-in (only checked when the caller
# happened to supply evidence.content, silently reverting to
# presence-only otherwise) -- every real caller omitted `content`, so
# in practice the mechanism verified nothing: a forged content_hash
# with no backing content still passed. Fail closed instead: content_hash
# present but content absent/unverifiable is now itself a failure.
CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
CONTENT_NOT_PROVIDED_FOR_HASH_VERIFICATION = "CONTENT_NOT_PROVIDED_FOR_HASH_VERIFICATION"

DEMO_MAX_EVIDENCE_AGE = timedelta(days=30)
ENV_MAX_EVIDENCE_AGE = "ACTASEAL_MAX_EVIDENCE_AGE_SECONDS"


def max_evidence_age() -> timedelta:
    """How old evidence may be. 30 days unless ACTASEAL_MAX_EVIDENCE_AGE_SECONDS says otherwise. A value that is not a
    positive, finite number raises: a typo must not quietly leave the window wide open."""
    import math
    import os

    raw = os.environ.get(ENV_MAX_EVIDENCE_AGE, "").strip()
    if not raw:
        return DEMO_MAX_EVIDENCE_AGE
    try:
        seconds = float(raw)
    except ValueError:
        raise ValueError(f"{ENV_MAX_EVIDENCE_AGE} must be a number of seconds, got {raw!r}") from None
    if not math.isfinite(seconds) or seconds <= 0 or seconds > 10 * 365 * 86400:
        raise ValueError(f"{ENV_MAX_EVIDENCE_AGE} must be a positive number of seconds (at most ten years), got {raw!r}")
    return timedelta(seconds=seconds)


def verify_evidence_packet(
    evidence: EvidencePacket,
    tenant_id: str,
    workspace_id: str,
    registry: EvidenceAuthorityRegistry,
) -> EvidenceVerificationResult:
    failure_codes: list[str] = []
    evidence_id = str(getattr(evidence, "evidence_id", "") or "")
    claim_type = str(getattr(evidence, "claim_type", "") or "")
    source_authority = str(getattr(evidence, "source_authority", "") or "")

    if getattr(evidence, "tenant_id", None) != tenant_id:
        failure_codes.append(EVIDENCE_TENANT_MISMATCH)
    if getattr(evidence, "workspace_id", None) != workspace_id:
        failure_codes.append(EVIDENCE_WORKSPACE_MISMATCH)

    try:
        registry.require_claim_registered(claim_type)
    except EvidenceAuthorityError as error:
        if error.code not in failure_codes:
            failure_codes.append(error.code)

    try:
        registry.require_authority_registered(source_authority)
    except EvidenceAuthorityError as error:
        if error.code not in failure_codes:
            failure_codes.append(error.code)

    if UNKNOWN_EVIDENCE_CLAIM not in failure_codes and UNKNOWN_EVIDENCE_AUTHORITY not in failure_codes:
        if not registry.is_authority_allowed_for_claim(claim_type, source_authority):
            failure_codes.append(EVIDENCE_AUTHORITY_MISMATCH)

    attestation_failure = verify_attestation(evidence, registry.public_key_for_authority(source_authority))
    if attestation_failure is not None:
        failure_codes.append(attestation_failure)

    if not str(getattr(evidence, "content_hash", "") or "").strip():
        failure_codes.append(MISSING_EVIDENCE_HASH)
    else:
        content = getattr(evidence, "content", None)
        if content is None:
            failure_codes.append(CONTENT_NOT_PROVIDED_FOR_HASH_VERIFICATION)
        else:
            actual_hash = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
            if actual_hash != str(evidence.content_hash):
                failure_codes.append(CONTENT_HASH_MISMATCH)
    if not str(getattr(evidence, "issuer", "") or "").strip():
        failure_codes.append(MISSING_EVIDENCE_ISSUER)

    freshness_timestamp = getattr(evidence, "freshness_timestamp", None)
    if not str(freshness_timestamp or "").strip():
        failure_codes.append(MISSING_EVIDENCE_FRESHNESS)
    else:
        failure_codes.extend(_freshness_failures(str(freshness_timestamp)))

    status = PASS if not failure_codes else FAIL
    return EvidenceVerificationResult(
        status=status,
        evidence_id=evidence_id,
        claim_type=claim_type,
        source_authority=source_authority,
        failure_codes=tuple(failure_codes),
        satisfied_claims={claim_type} if status == PASS else set(),
        money=getattr(evidence, "money", None) if status == PASS else None,
    )


def verify_evidence_set(
    evidence_packets: list[EvidencePacket],
    required_claims: set[str],
    tenant_id: str,
    workspace_id: str,
    registry: EvidenceAuthorityRegistry,
) -> EvidenceSetVerificationResult:
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    packet_results: list[EvidenceVerificationResult] = []
    for evidence in evidence_packets:
        result = verify_evidence_packet(evidence, tenant_id, workspace_id, registry)
        evidence_id = result.evidence_id
        if evidence_id in seen_ids:
            duplicate_ids.add(evidence_id)
            result = _with_failure(result, DUPLICATE_EVIDENCE_ID)
        seen_ids.add(evidence_id)
        packet_results.append(result)

    if duplicate_ids:
        packet_results = [
            _with_failure(result, DUPLICATE_EVIDENCE_ID)
            if result.evidence_id in duplicate_ids
            else result
            for result in packet_results
        ]

    satisfied_claims: set[str] = set()
    claim_authorities: dict[str, str] = {}
    claim_money: dict[str, MoneyPacket] = {}
    failures: list[dict] = []
    invalid_evidence_ids: list[str] = []
    for result in packet_results:
        if result.status == PASS:
            satisfied_claims.update(result.satisfied_claims)
            claim_authorities[result.claim_type] = result.source_authority
            if result.money is not None:
                claim_money[result.claim_type] = result.money
        else:
            invalid_evidence_ids.append(result.evidence_id)
            failures.append(result.to_failure_dict())

    missing_claims = set(required_claims) - satisfied_claims
    for claim in sorted(missing_claims):
        failures.append(
            {
                "evidence_id": None,
                "claim_type": claim,
                "source_authority": None,
                "failure_codes": [REQUIRED_EVIDENCE_MISSING],
            }
        )

    status = PASS if not failures else FAIL
    return EvidenceSetVerificationResult(
        status=status,
        satisfied_claims=satisfied_claims,
        claim_authorities=claim_authorities,
        missing_claims=missing_claims,
        invalid_evidence_ids=invalid_evidence_ids,
        failures=failures,
        claim_money=claim_money,
    )


def _freshness_failures(raw_timestamp: str) -> list[str]:
    try:
        timestamp = _parse_timestamp(raw_timestamp)
    except ValueError:
        return [INVALID_EVIDENCE_TIMESTAMP]

    now = datetime.now(timezone.utc)
    if timestamp > now:
        return [FUTURE_EVIDENCE_TIMESTAMP]
    if now - timestamp > max_evidence_age():
        return [STALE_EVIDENCE]
    return []


def _parse_timestamp(raw_timestamp: str) -> datetime:
    normalized = raw_timestamp.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("freshness_timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _with_failure(result: EvidenceVerificationResult, code: str) -> EvidenceVerificationResult:
    failure_codes = list(result.failure_codes)
    if code not in failure_codes:
        failure_codes.append(code)
    return EvidenceVerificationResult(
        status=FAIL,
        evidence_id=result.evidence_id,
        claim_type=result.claim_type,
        source_authority=result.source_authority,
        failure_codes=tuple(failure_codes),
        satisfied_claims=set(),
    )
