from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any, overload

_I_JSON_MAX = 2**53 - 1
_BMP_MAX = 0xFFFF


class UnsignableValueError(ValueError):
    """v1 was asked to sign or hash a value it refuses: a float, a non-BMP
    object key, or an integer outside +/-(2**53 - 1). `reason` is one of
    "float", "non_bmp_key", "integer_range"; the message never repeats
    the value, so it is safe to show a caller who supplied it."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _canonical_value(value: object, *, strict: bool = True) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if strict:
            raise UnsignableValueError(
                "float",
                "canonical JSON v1 does not sign floats: json.dumps writes "
                "1.0, -0.0 and 1e-05 where RFC 8785 writes 1, 0 and 0.00001; "
                "pass the number as a string or a Decimal",
            )
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if strict and abs(value) > _I_JSON_MAX:
            raise UnsignableValueError(
                "integer_range",
                "canonical JSON v1 does not sign an integer outside the I-JSON safe "
                "range (abs > 2**53 - 1), where v1 and RFC 8785 write different digits; "
                "pass it as a string",
            )
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            text = str(key)
            if strict and any(ord(ch) > _BMP_MAX for ch in text):
                raise UnsignableValueError(
                    "non_bmp_key",
                    "canonical JSON v1 does not sign non-BMP object keys: it sorts "
                    "by code point, RFC 8785 by UTF-16 code unit",
                )
            out[text] = _canonical_value(item, strict=strict)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, strict=strict) for item in value]
    return value


def signable_float(value: float) -> str:
    """A float as the decimal string of its shortest round-trip digits
    ('1.0', '0.0000001', '12.5'): how a measured number goes into
    anything v1 signs, since v1 refuses floats."""
    if not math.isfinite(value):
        raise ValueError("canonical JSON does not allow NaN or Infinity")
    return format(Decimal(repr(float(value))), "f")


def signable_seconds(seconds: float) -> int | str:
    """A duration for a signed payload: whole seconds as an integer,
    anything else as the decimal string of its shortest digits."""
    return int(seconds) if float(seconds).is_integer() else signable_float(seconds)


@overload
def signable_tree(value: dict[str, Any]) -> dict[str, Any]: ...
@overload
def signable_tree(value: object) -> object: ...
def signable_tree(value: object) -> object:
    """`value` with every float replaced by signable_float, containers
    copied. Call it on a payload before v1 signs or hashes it."""
    if isinstance(value, float):
        return signable_float(value)
    if isinstance(value, dict):
        return {k: signable_tree(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [signable_tree(v) for v in value]
    return value


def canonical_json_dumps(value: object) -> str:
    """v1, what receipts and ledger events are signed with. Refuses what
    it cannot write the way RFC 8785 does: floats, non-BMP keys and integers
    beyond +/-(2**53-1). Use
    canonical_json_dumps_v2 for new formats, and
    canonical_json_dumps_existing only to re-check bytes that were
    already written."""
    return _dumps(value, strict=True)


def canonical_json_dumps_existing(value: object) -> str:
    """The v1 bytes of data that already exists (a ledger file written
    before v1 refused floats holds `ttl_seconds: 3600.0`). Verification
    only: it reproduces what was signed, never to sign anything new."""
    return _dumps(value, strict=False)


def _dumps(value: object, *, strict: bool) -> str:
    try:
        return json.dumps(
            _canonical_value(value, strict=strict),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except ValueError as exc:
        if isinstance(exc, UnsignableValueError):
            raise
        raise ValueError("canonical JSON does not allow NaN or Infinity") from exc


def canonical_json_hash_existing(value: object) -> str:
    """sha256 of canonical_json_dumps_existing; see there."""
    return _payload_sha256(canonical_json_dumps_existing(value).encode("utf-8"))


def canonical_json_hash(value: object) -> str:
    # py/weak-sensitive-data-hashing false positive: this hashes the
    # CANONICAL JSON BYTES OF A PAYLOAD (a receipt, a ledger event, an
    # evidence packet) for the tamper-evident hash chain and signature
    # scheme -- an integrity digest over public/already-signed data, not
    # a credential, password, or anything secret. sha256 is the correct
    # primitive for this (fast, deterministic, exactly what every
    # existing signed receipt/ledger entry was hashed with); a
    # slow/salted password-hashing KDF would be wrong here, not safer --
    # it would break byte-for-byte reproducibility and signature
    # verification against every already-issued receipt.
    return _payload_sha256(canonical_json_dumps(value).encode("utf-8"))


def _payload_sha256(encoded: bytes) -> str:
    """The one place canonical payload bytes are hashed, for both canonical_json_hash and
    canonical_json_hash_existing."""
    # This hashes canonical evidence-chain payload bytes for the receipt/ledger
    # hash chain, never a password or credential -- SHA-256 is the correct, fast,
    # content-addressing hash for that job, the opposite of what this query warns
    # about. Hash function intentionally unchanged.
    # codeql[py/weak-sensitive-data-hashing]
    return hashlib.sha256(encoded).hexdigest()


# --- v2: RFC 8785 (JSON Canonicalization Scheme) conformant path -----------
#
# v1 above (canonical_json_dumps) is what every already-signed receipt was
# hashed and signed with, and stays byte-for-byte unchanged so old fixtures
# keep verifying. It diverges from RFC 8785 in two ways, which is why it
# now refuses floats and non-BMP keys outright (C14; a ledger event used
# to carry `ttl_seconds: 3600.0`, which v1 wrote as "3600.0" and RFC 8785
# writes as "3600"): (1) it sorts object keys by Python
# codepoint order, not RFC 8785's UTF-16 code-unit order; (2) it lets
# json.dumps serialize floats/ints with Python's number formatting, not the
# ECMAScript Number::toString format RFC 8785 mandates. v2 fixes both.
# Callers that need conformant JCS bytes (e.g. new integrations) should use
# canonical_json_dumps_v2 explicitly; nothing existing switches to it.


def _utf16_sort_key(key: str) -> tuple[int, ...]:
    units: list[int] = []
    for ch in key:
        codepoint = ord(ch)
        if codepoint > 0xFFFF:
            codepoint -= 0x10000
            units.append(0xD800 + (codepoint >> 10))
            units.append(0xDC00 + (codepoint & 0x3FF))
        else:
            units.append(codepoint)
    return tuple(units)


def _es_number_to_string(value: float) -> str:
    """ECMAScript Number::toString, per RFC 8785 section 3.2.2.3."""
    if math.isnan(value) or math.isinf(value):
        raise ValueError("canonical JSON does not allow NaN or Infinity")
    if value == 0:
        return "0"
    negative = value < 0
    magnitude = -value if negative else value
    digits_tuple = Decimal(repr(magnitude)).normalize().as_tuple()
    digits = "".join(str(d) for d in digits_tuple.digits)
    k = len(digits)
    n = digits_tuple.exponent + k
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        exponent = n - 1
        mantissa = digits[0] + ("." + digits[1:] if k > 1 else "")
        body = mantissa + "e" + ("+" if exponent >= 0 else "-") + str(abs(exponent))
    return ("-" if negative else "") + body


def _require_exact_double(value: int) -> None:
    """A JSON number under RFC 8785 is an IEEE-754 double. An integer
    with no exact double (anything that needs more than 53 significant
    bits) would be written as a neighbouring number's text, so two
    different integers would canonicalize, hash and sign identically.
    Refuse it; the caller passes such a value as a string."""
    try:
        exact = int(float(value)) == value
    except OverflowError:
        exact = False
    if not exact:
        raise ValueError(
            f"canonical JSON v2 cannot represent the integer {value} exactly as a number; "
            "pass it as a string"
        )


def _canonical_value_v2(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        as_float = float(value)
        # A Decimal is written as the double it converts to. If that
        # double is a different number, refuse rather than sign a value
        # other than the one given.
        if not math.isfinite(as_float) or Decimal(repr(as_float)) != value:
            raise ValueError(
                f"canonical JSON v2 cannot represent {value} exactly as a number; "
                "pass it as a string"
            )
        return _es_number_to_string(as_float)
    if isinstance(value, int):
        _require_exact_double(value)
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, dict):
        return {str(k): _canonical_value_v2(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value_v2(item) for item in value]
    return value


def _encode_v2(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int) and not isinstance(value, bool):
        _require_exact_double(value)
        return _es_number_to_string(float(value))
    if isinstance(value, float):
        return _es_number_to_string(value)
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: _utf16_sort_key(kv[0]))
        body = ",".join(f"{json.dumps(k, ensure_ascii=False)}:{_encode_v2(v)}" for k, v in items)
        return "{" + body + "}"
    if isinstance(value, list):
        return "[" + ",".join(_encode_v2(item) for item in value) + "]"
    raise TypeError(f"canonical JSON v2 cannot encode {type(value)!r}")


def canonical_json_dumps_v2(value: object) -> str:
    """RFC 8785 JCS-conformant canonical JSON. See module docstring above
    for why this is additive rather than a v1 replacement."""
    return _encode_v2(_canonical_value_v2(value))


def canonical_json_hash_v2(value: object) -> str:
    encoded = canonical_json_dumps_v2(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
