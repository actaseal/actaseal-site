from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from actaseal.core.decisions import (
    ALLOW,
    APPROVAL_REQUIRED,
    ASK_MORE_EVIDENCE,
    BLOCK,
    BLOCK_EXECUTION,
    ESCALATE,
    ESCALATE_FOR_REVIEW,
    EXECUTION_PERMITTED,
    PAUSE_FOR_APPROVAL,
    PAUSE_FOR_EVIDENCE,
)
from actaseal.attestation.sources import ATTESTATION_VERIFIED, EVIDENCE_ATTESTATION_UNVERIFIED
from actaseal.core.money import MoneyPacket
from actaseal.core.packets import ActionPacket, ActorPacket
from actaseal.evidence.results import EvidenceSetVerificationResult
from actaseal.ledger.idempotency import (
    CLEAR,
    CONFLICT,
    DUPLICATE,
    IdempotencyCheckResult,
)
from actaseal.policy.schema import ActionPolicy, CompiledPolicy, SegmentRule


@dataclass(frozen=True)
class PolicyEvaluation:
    verdict: str
    enforcement_action: str
    reason_code: str
    required_evidence_missing: tuple[str, ...]
    approval_required: bool
    allowed_to_execute: bool


def evaluate_action_policy(
    action: ActionPacket,
    actor: ActorPacket,
    policy: CompiledPolicy,
    evidence_claims: set[str],
    evidence_authorities: dict[str, str],
    idempotency_clear: bool,
    attested_money: MoneyPacket | None = None,
    attestation_status: str | None = None,
    segment_inputs: Mapping[str, object] | None = None,
) -> PolicyEvaluation:
    action_policy = policy.action_policies.get(getattr(action, "action_type", None))
    if action_policy is None:
        return _closed(BLOCK, "UNKNOWN_ACTION_TYPE")

    money = getattr(action, "money", None)
    if action_policy.money.amount_required and not isinstance(money, MoneyPacket):
        return _closed(BLOCK, "MALFORMED_MONEY_PACKET")
    if isinstance(money, MoneyPacket):
        if action_policy.money.currency_required and money.currency not in action_policy.money.allowed_currencies:
            return _closed(BLOCK, "CURRENCY_NOT_ALLOWED")
        if action_policy.money.positive_required and money.amount <= Decimal("0"):
            return _closed(BLOCK, "NON_POSITIVE_AMOUNT")

    if not idempotency_clear:
        return _closed(BLOCK, "IDEMPOTENCY_NOT_CLEAR")

    missing = _missing_evidence(action_policy, evidence_claims, evidence_authorities)
    if missing:
        return PolicyEvaluation(
            verdict=ASK_MORE_EVIDENCE,
            enforcement_action=PAUSE_FOR_EVIDENCE,
            reason_code="REQUIRED_EVIDENCE_MISSING",
            required_evidence_missing=missing,
            approval_required=False,
            allowed_to_execute=False,
        )

    # Attestation gate: WHO attests, checked before any amount check. None
    # means no attestation registry is configured (pre-attestation
    # pipeline); any configured result other than VERIFIED fails closed.
    if attestation_status is not None and attestation_status != ATTESTATION_VERIFIED:
        return _closed(BLOCK, EVIDENCE_ATTESTATION_UNVERIFIED)

    if isinstance(money, MoneyPacket) and action_policy.money.amount_required:
        if attested_money is None and action_policy.money.amount_source == "caller":
            attested_money = money
        if attested_money is None:
            return PolicyEvaluation(
                verdict=ASK_MORE_EVIDENCE,
                enforcement_action=PAUSE_FOR_EVIDENCE,
                reason_code="AMOUNT_NOT_ATTESTED",
                required_evidence_missing=(),
                approval_required=False,
                allowed_to_execute=False,
            )
        if attested_money != money:
            return _closed(BLOCK, "AMOUNT_EVIDENCE_MISMATCH")

        segment = matching_segment(action_policy, segment_inputs)
        limits = segment.limits if segment is not None else action_policy.limits
        hard_block_above = limits["hard_block_above"]
        approval_required_above = limits["approval_required_above"]
        auto_allow_max = limits["auto_allow_max"]
        if hard_block_above is not None and money.amount > hard_block_above:
            return _closed(BLOCK, "AMOUNT_ABOVE_HARD_BLOCK")
        if approval_required_above is not None and money.amount > approval_required_above:
            return PolicyEvaluation(
                verdict=APPROVAL_REQUIRED,
                enforcement_action=PAUSE_FOR_APPROVAL,
                reason_code="AMOUNT_REQUIRES_APPROVAL",
                required_evidence_missing=(),
                approval_required=True,
                allowed_to_execute=False,
            )
        if auto_allow_max is not None and money.amount <= auto_allow_max:
            return PolicyEvaluation(
                verdict=ALLOW,
                enforcement_action=EXECUTION_PERMITTED,
                reason_code="POLICY_ALLOW",
                required_evidence_missing=(),
                approval_required=False,
                allowed_to_execute=True,
            )
        # Money is present but matched no auto-allow band. Fail closed.
        return PolicyEvaluation(
            verdict=APPROVAL_REQUIRED,
            enforcement_action=PAUSE_FOR_APPROVAL,
            reason_code="AMOUNT_OUTSIDE_AUTO_ALLOW_BAND",
            required_evidence_missing=(),
            approval_required=True,
            allowed_to_execute=False,
        )

    if action_policy.approval.always_required:
        return PolicyEvaluation(
            verdict=APPROVAL_REQUIRED,
            enforcement_action=PAUSE_FOR_APPROVAL,
            reason_code="ACTION_TYPE_REQUIRES_APPROVAL",
            required_evidence_missing=(),
            approval_required=True,
            allowed_to_execute=False,
        )

    return PolicyEvaluation(
        verdict=ALLOW,
        enforcement_action=EXECUTION_PERMITTED,
        reason_code="POLICY_ALLOW",
        required_evidence_missing=(),
        approval_required=False,
        allowed_to_execute=True,
    )


def evaluate_with_verified_evidence(
    action: ActionPacket,
    actor: ActorPacket,
    policy: CompiledPolicy,
    evidence_result: EvidenceSetVerificationResult,
    idempotency_clear: bool,
) -> PolicyEvaluation:
    evidence_claims, evidence_authorities = evidence_result.to_policy_inputs()
    return evaluate_action_policy(
        action=action,
        actor=actor,
        policy=policy,
        evidence_claims=evidence_claims,
        evidence_authorities=evidence_authorities,
        idempotency_clear=idempotency_clear,
        attested_money=evidence_result.attested_money(),
    )


def evaluate_action_policy_with_idempotency(
    action: ActionPacket,
    actor: ActorPacket,
    policy: CompiledPolicy,
    evidence_result: EvidenceSetVerificationResult,
    idempotency_result: IdempotencyCheckResult,
    attestation_status: str | None = None,
    segment_inputs: Mapping[str, object] | None = None,
) -> PolicyEvaluation:
    if idempotency_result.status == DUPLICATE:
        return _closed(BLOCK, idempotency_result.reason_code)
    if idempotency_result.status not in (CLEAR, CONFLICT) or (
        idempotency_result.status == CLEAR and not idempotency_result.allowed_to_continue
    ):
        return _closed(BLOCK, idempotency_result.reason_code)

    evidence_claims, evidence_authorities = evidence_result.to_policy_inputs()
    evaluation = evaluate_action_policy(
        action=action,
        actor=actor,
        policy=policy,
        evidence_claims=evidence_claims,
        evidence_authorities=evidence_authorities,
        idempotency_clear=True,
        attested_money=evidence_result.attested_money(),
        attestation_status=attestation_status,
        segment_inputs=segment_inputs,
    )
    if idempotency_result.status == CONFLICT and evaluation.verdict != BLOCK:
        # A conflict with an earlier action goes to a person, unless the policy refuses the
        # action outright: then the stricter answer wins, so no approver can pay out an amount
        # the policy blocks.
        return _closed(ESCALATE, idempotency_result.reason_code)
    return evaluation


def idempotency_clear_from_ledger(idempotency_result: IdempotencyCheckResult) -> bool:
    return idempotency_result.status == CLEAR and idempotency_result.allowed_to_continue


def _missing_evidence(
    action_policy: ActionPolicy,
    evidence_claims: set[str],
    evidence_authorities: dict[str, str],
) -> tuple[str, ...]:
    missing: list[str] = []
    for requirement in action_policy.required_evidence:
        if requirement.claim not in evidence_claims:
            missing.append(requirement.claim)
            continue
        if evidence_authorities.get(requirement.claim) != requirement.authority:
            missing.append(requirement.claim)
    return tuple(missing)


def _closed(verdict: str, reason_code: str) -> PolicyEvaluation:
    enforcement = {
        BLOCK: BLOCK_EXECUTION,
        ASK_MORE_EVIDENCE: PAUSE_FOR_EVIDENCE,
        APPROVAL_REQUIRED: PAUSE_FOR_APPROVAL,
        ESCALATE: ESCALATE_FOR_REVIEW,
    }.get(verdict, BLOCK_EXECUTION)
    return PolicyEvaluation(
        verdict=verdict,
        enforcement_action=enforcement,
        reason_code=reason_code,
        required_evidence_missing=(),
        approval_required=verdict == APPROVAL_REQUIRED,
        allowed_to_execute=False,
    )


def matching_segment(
    action_policy: ActionPolicy, inputs: Mapping[str, object] | None
) -> SegmentRule | None:
    """The first segment whose every condition holds for ``inputs`` (customer_tier,
    category, first_order, order_age_days), or None. A condition on something the
    inputs do not say never holds."""
    if not action_policy.segments or not inputs:
        return None
    for segment in action_policy.segments:
        if all(_condition_holds(key, expected, inputs) for key, expected in segment.when.items()):
            return segment
    return None


def _condition_holds(key: str, expected: object, inputs: Mapping[str, object]) -> bool:
    if key in ("order_age_days_min", "order_age_days_max"):
        age = inputs.get("order_age_days")
        if not isinstance(age, int) or not isinstance(expected, int):
            return False
        return age >= expected if key == "order_age_days_min" else age <= expected
    return inputs.get(key) == expected
