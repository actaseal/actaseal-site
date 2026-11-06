from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from actaseal.core.canonical_json import canonical_json_hash
from actaseal.core.money import SUPPORTED_CURRENCIES
from actaseal.policy.schema import (
    CompiledPolicy,
    ActionPolicy,
    ApprovalRule,
    ConnectorModeRule,
    EvidenceRequirement,
    INVALID_POLICY_CURRENCY,
    INVALID_POLICY_LIMIT,
    INVALID_POLICY_SCHEMA,
    MISSING_POLICY_ID,
    MISSING_POLICY_VERSION,
    MoneyRule,
    POLICY_COMPILE_FAILED,
    PolicyValidationError,
    SegmentRule,
)

COMPILER_VERSION = "declarative-policy-compiler.v1"
LIMIT_FIELDS = ("auto_allow_max", "approval_required_above", "hard_block_above")


def load_policy_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, "policy file must contain a JSON object")
    return raw


def compile_policy(raw: dict[str, Any]) -> CompiledPolicy:
    try:
        policy_id = _required_text(raw.get("policy_id"), "policy_id", MISSING_POLICY_ID)
        policy_version = _required_text(raw.get("policy_version"), "policy_version", MISSING_POLICY_VERSION)
        compiler_version = str(raw.get("compiler_version") or COMPILER_VERSION)
        action_types = _required_list(raw.get("action_types"), "action_types")
        raw_action_policies = _required_dict(raw.get("action_policies"), "action_policies")

        action_policies: dict[str, ActionPolicy] = {}
        for action_type in action_types:
            if not isinstance(action_type, str) or not action_type.strip():
                raise PolicyValidationError(INVALID_POLICY_SCHEMA, "action_types must contain non-empty strings", field="action_types")
            parsed_action_type = action_type.strip()
            raw_action = _required_dict(raw_action_policies.get(parsed_action_type), f"action_policies.{parsed_action_type}")
            action_policies[parsed_action_type] = _compile_action_policy(
                policy_id,
                policy_version,
                parsed_action_type,
                raw_action,
                compiler_version,
            )

        extra_actions = set(raw_action_policies) - set(action_policies)
        if extra_actions:
            raise PolicyValidationError(
                INVALID_POLICY_SCHEMA,
                "action_policies contains actions not declared in action_types",
                field="action_policies",
                details={"extra_actions": sorted(extra_actions)},
            )

        return CompiledPolicy(
            policy_id=policy_id,
            policy_version=policy_version,
            action_policies=action_policies,
            compiler_version=compiler_version,
        )
    except PolicyValidationError:
        raise
    except Exception as exc:
        raise PolicyValidationError(POLICY_COMPILE_FAILED, "policy compilation failed") from exc


def policy_hash(compiled: CompiledPolicy) -> str:
    return canonical_json_hash(compiled.to_dict())


def _compile_action_policy(
    policy_id: str,
    policy_version: str,
    action_type: str,
    raw_action: dict[str, Any],
    compiler_version: str,
) -> ActionPolicy:
    money = _compile_money_rule(_required_dict(raw_action.get("money"), f"{action_type}.money"))
    limits = _compile_limits(_required_dict(raw_action.get("limits"), f"{action_type}.limits"))
    required_evidence = _compile_evidence(_required_list(raw_action.get("required_evidence"), f"{action_type}.required_evidence"))
    forbidden = _compile_forbidden(_required_list(raw_action.get("forbidden"), f"{action_type}.forbidden"))
    approval = _compile_approval(_required_dict(raw_action.get("approval"), f"{action_type}.approval"))
    connector = _compile_connector(_required_dict(raw_action.get("connector"), f"{action_type}.connector"))
    segments = _compile_segments(raw_action.get("segments"), action_type)
    return ActionPolicy(
        policy_id=policy_id,
        policy_version=policy_version,
        action_type=action_type,
        money=money,
        limits=limits,
        required_evidence=required_evidence,
        forbidden=forbidden,
        approval=approval,
        connector=connector,
        compiler_version=compiler_version,
        segments=segments,
    )


SEGMENT_CONDITIONS = {
    "customer_tier": str, "category": str, "first_order": bool, "order_age_days_min": int,
    "order_age_days_max": int,
}


def _compile_segments(raw: Any, action_type: str) -> tuple[SegmentRule, ...]:
    if raw is None:
        return ()
    field = f"{action_type}.segments"
    segments: list[SegmentRule] = []
    for item in _required_list(raw, field):
        entry = _required_dict(item, field)
        name = _required_text(entry.get("name"), f"{field}.name", INVALID_POLICY_SCHEMA)
        if any(s.name == name for s in segments):
            raise PolicyValidationError(INVALID_POLICY_SCHEMA, "repeated segment", field=field)
        when = _required_dict(entry.get("when"), f"{field}.when")
        if not when:
            raise PolicyValidationError(INVALID_POLICY_SCHEMA, "empty segment", field=field)
        conditions: dict[str, object] = {}
        for key, value in when.items():
            kind = SEGMENT_CONDITIONS.get(key)
            negative = isinstance(value, int) and not isinstance(value, bool) and value < 0
            if kind is None or type(value) is not kind or negative:
                raise PolicyValidationError(
                    INVALID_POLICY_SCHEMA, f"bad segment condition {key!r}", field=field
                )
            conditions[key] = value.strip().lower() if isinstance(value, str) else value
        limits = _compile_limits(_required_dict(entry.get("limits"), f"{field}.limits"))
        segments.append(SegmentRule(name=name, when=conditions, limits=limits))
    return tuple(segments)


def _compile_money_rule(raw: dict[str, Any]) -> MoneyRule:
    allowed_currencies = _required_list(raw.get("allowed_currencies"), "money.allowed_currencies")
    parsed_currencies: list[str] = []
    for currency in allowed_currencies:
        parsed = _required_text(currency, "money.allowed_currencies", INVALID_POLICY_CURRENCY).upper()
        if parsed not in SUPPORTED_CURRENCIES:
            raise PolicyValidationError(
                INVALID_POLICY_CURRENCY,
                "policy contains unsupported currency",
                field="money.allowed_currencies",
                details={"currency": parsed, "supported": sorted(SUPPORTED_CURRENCIES)},
            )
        parsed_currencies.append(parsed)
    return MoneyRule(
        amount_required=_required_bool(raw.get("amount_required"), "money.amount_required"),
        currency_required=_required_bool(raw.get("currency_required"), "money.currency_required"),
        allowed_currencies=tuple(parsed_currencies),
        positive_required=_required_bool(raw.get("positive_required"), "money.positive_required"),
        amount_source=_amount_source(raw.get("amount_source", "attested")),
    )


AMOUNT_SOURCES = ("attested", "caller")


def _amount_source(value: Any) -> str:
    if value not in AMOUNT_SOURCES:
        raise PolicyValidationError(
            INVALID_POLICY_SCHEMA,
            "money.amount_source must be \"attested\" or \"caller\"",
            field="money.amount_source",
        )
    return value


def _compile_limits(raw: dict[str, Any]) -> dict[str, Decimal | None]:
    limits: dict[str, Decimal | None] = {}
    for field in LIMIT_FIELDS:
        if field not in raw:
            raise PolicyValidationError(INVALID_POLICY_SCHEMA, "missing policy limit", field=f"limits.{field}")
        limits[field] = _parse_decimal_or_none(raw[field], f"limits.{field}")
    auto_allow = limits["auto_allow_max"]
    approval_required = limits["approval_required_above"]
    hard_block = limits["hard_block_above"]
    if auto_allow is not None and approval_required is not None and auto_allow > approval_required:
        raise PolicyValidationError(INVALID_POLICY_LIMIT, "auto allow limit cannot exceed approval threshold", field="limits.auto_allow_max")
    if hard_block is not None and approval_required is not None and hard_block < approval_required:
        raise PolicyValidationError(INVALID_POLICY_LIMIT, "hard block limit cannot be below approval threshold", field="limits.hard_block_above")
    return limits


def _compile_evidence(raw: list[Any]) -> tuple[EvidenceRequirement, ...]:
    requirements: list[EvidenceRequirement] = []
    for item in raw:
        item_dict = _required_dict(item, "required_evidence")
        requirements.append(
            EvidenceRequirement(
                claim=_required_text(item_dict.get("claim"), "required_evidence.claim", INVALID_POLICY_SCHEMA),
                authority=_required_text(item_dict.get("authority"), "required_evidence.authority", INVALID_POLICY_SCHEMA),
            )
        )
    return tuple(requirements)


def _compile_forbidden(raw: list[Any]) -> tuple[str, ...]:
    return tuple(_required_text(item, "forbidden", INVALID_POLICY_SCHEMA) for item in raw)


def _compile_approval(raw: dict[str, Any]) -> ApprovalRule:
    if "required_role" not in raw:
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, "missing approval role declaration", field="approval.required_role")
    required_role = raw["required_role"]
    # Optional, defaults False -- existing policy JSON with no
    # "require_webauthn" key compiles unchanged (backward compatible).
    require_webauthn_raw = raw.get("require_webauthn", False)
    if not isinstance(require_webauthn_raw, bool):
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, "approval.require_webauthn must be a boolean", field="approval.require_webauthn")
    always_required = raw.get("always_required", False)
    if not isinstance(always_required, bool):
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, "approval.always_required must be a boolean", field="approval.always_required")
    if required_role is None:
        if always_required:
            raise PolicyValidationError(INVALID_POLICY_SCHEMA, "approval.always_required needs a required_role", field="approval.required_role")
        return ApprovalRule(required_role=None, require_webauthn=require_webauthn_raw)
    return ApprovalRule(
        required_role=_required_text(required_role, "approval.required_role", INVALID_POLICY_SCHEMA),
        require_webauthn=require_webauthn_raw,
        always_required=always_required,
    )


def _compile_connector(raw: dict[str, Any]) -> ConnectorModeRule:
    return ConnectorModeRule(
        executed_must_be_false=_required_bool(raw.get("executed_must_be_false"), "connector.executed_must_be_false"),
        mutating_must_be_false=_required_bool(raw.get("mutating_must_be_false"), "connector.mutating_must_be_false"),
    )


def _parse_decimal_or_none(value: Any, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise PolicyValidationError(INVALID_POLICY_LIMIT, "policy limit must be a finite Decimal-compatible string", field=field)
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PolicyValidationError(INVALID_POLICY_LIMIT, "policy limit must be a finite Decimal-compatible string", field=field) from exc
    if not parsed.is_finite() or parsed < 0:
        raise PolicyValidationError(INVALID_POLICY_LIMIT, "policy limit must be finite and non-negative", field=field)
    return parsed


def _required_text(value: Any, field: str, code: str) -> str:
    if value is None or not str(value).strip():
        raise PolicyValidationError(code, f"{field} is required", field=field)
    return str(value).strip()


def _required_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, f"{field} must be an object", field=field)
    return value


def _required_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, f"{field} must be a list", field=field)
    return value


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyValidationError(INVALID_POLICY_SCHEMA, f"{field} must be a boolean", field=field)
    return value
