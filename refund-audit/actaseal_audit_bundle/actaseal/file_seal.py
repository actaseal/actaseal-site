"""Seal a set of files -- logs, an evidence pack, an audit submission -- so
anyone can later check, offline:

  * the files are byte-for-byte unchanged (sha256 per file);
  * when the seal existed (an RFC 3161 timestamp from an external TSA over
    the seal's hash; the local clock in `created_at` is informative only);
  * who sealed them (optional Ed25519 signature, checked against a public
    key the verifier already trusts -- a signature alone only proves the
    seal is self-consistent, since anyone can re-seal with their own key);
  * no seal in a chain was dropped or rewritten (`previous_seal_sha256`,
    for daily log rotation).

Seal document (format actaseal.file-seal.v1):

    {"format", "created_at", "label", "files": [{"path", "sha256", "size"}],
     "previous_seal_sha256",                    <- the body; seal_sha256 is
     "seal_sha256",                                its canonical-JSON sha256
     "tsa_anchor": TsaAnchor.to_dict() | null,  <- over the seal_sha256 bytes
     "signature": {"algorithm", "key_id", "public_key_hex", "signature_hex"} | null}

Paths are POSIX paths relative to a base directory. Building fails closed
on symlinks, special files and paths outside the base; verifying fails
closed on absolute or `..` paths, so a crafted seal cannot point the
verifier outside the base. Only the files the seal lists are checked:
files added under the base later are not reported.

The TSA certificate is trusted only from the CA bundled with this package
for the default TSA pool, or a CA the verifier passes explicitly -- never
from the `ca_cert_path` recorded inside the seal.
"""
from __future__ import annotations

import copy
import hashlib
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from collections.abc import Iterable
from typing import Any

from actaseal.core.canonical_json import canonical_json_dumps

SEAL_FORMAT = "actaseal.file-seal.v1"
SIGNATURE_DOMAIN = b"actaseal.file-seal.v1\x00"
BODY_FIELDS = ("format", "created_at", "label", "files", "previous_seal_sha256")

TIMESTAMP_OK = "OK"
TIMESTAMP_MISSING_STATUS = "UNTIMESTAMPED"
TIMESTAMP_INVALID = "INVALID"


class SealError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# ---------------------------------------------------------------- hashing

def seal_hash(seal: dict) -> str:
    """sha256 over the canonical JSON of the seal body (never trusted from
    the seal's own `seal_sha256` field)."""
    body = {k: seal.get(k) for k in BODY_FIELDS}
    return hashlib.sha256(canonical_json_dumps(body).encode("utf-8")).hexdigest()


def _hash_file(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


# ---------------------------------------------------------------- building

def _collect(paths: Iterable[str | os.PathLike], base: str) -> dict[str, str]:
    """rel posix path -> absolute path, for every regular file under `paths`."""
    found: dict[str, str] = {}

    def rel_of(abs_path: str) -> str:
        rel = os.path.relpath(abs_path, base)
        if rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel):
            raise SealError("SEAL_PATH_OUTSIDE_BASE", f"{abs_path} is not under the base directory {base}")
        return PurePosixPath(*Path(rel).parts).as_posix()

    def add_file(abs_path: str) -> None:
        if os.path.islink(abs_path):
            raise SealError("SEAL_SYMLINK_REFUSED", f"{abs_path} is a symlink; seal the target itself")
        if not stat.S_ISREG(os.lstat(abs_path).st_mode):
            raise SealError("SEAL_INPUT_UNSUPPORTED", f"{abs_path} is not a regular file")
        found[rel_of(abs_path)] = abs_path

    for p in paths:
        abs_path = os.path.abspath(os.fspath(p))
        if not os.path.lexists(abs_path):
            raise SealError("SEAL_INPUT_MISSING", f"{abs_path} does not exist")
        rel_of(abs_path)
        if os.path.islink(abs_path):
            raise SealError("SEAL_SYMLINK_REFUSED", f"{abs_path} is a symlink; seal the target itself")
        if os.path.isdir(abs_path):
            for root, dirs, files in os.walk(abs_path, followlinks=False):
                for d in dirs:
                    if os.path.islink(os.path.join(root, d)):
                        raise SealError("SEAL_SYMLINK_REFUSED", f"{os.path.join(root, d)} is a symlink")
                for name in files:
                    add_file(os.path.join(root, name))
        else:
            add_file(abs_path)
    if not found:
        raise SealError("SEAL_NO_FILES", "nothing to seal: the given paths contain no files")
    return found


def _check_previous(previous: Any) -> str:
    if not isinstance(previous, dict) or previous.get("format") != SEAL_FORMAT:
        raise SealError("PREVIOUS_SEAL_INVALID", "the previous seal is not an actaseal.file-seal.v1 document")
    digest = seal_hash(previous)
    if digest != previous.get("seal_sha256"):
        raise SealError("PREVIOUS_SEAL_INVALID", "the previous seal's content does not match its seal_sha256")
    return digest


def build_seal(paths: Iterable[str | os.PathLike], *, base: str | os.PathLike, label: str | None = None,
               previous: dict | None = None, created_at: str | None = None) -> dict:
    """Hash every file under `paths` (relative to `base`) into an unsigned,
    untimestamped seal. `previous` chains this seal to the one before it."""
    base_abs = os.path.abspath(os.fspath(base))
    if not os.path.isdir(base_abs):
        raise SealError("SEAL_INPUT_MISSING", f"base directory {base_abs} does not exist")
    previous_hash = _check_previous(previous) if previous is not None else None
    files = []
    for rel, abs_path in sorted(_collect(paths, base_abs).items()):
        digest, size = _hash_file(abs_path)
        files.append({"path": rel, "sha256": digest, "size": size})
    seal = {
        "format": SEAL_FORMAT,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": label,
        "files": files,
        "previous_seal_sha256": previous_hash,
    }
    seal["seal_sha256"] = seal_hash(seal)
    seal["tsa_anchor"] = None
    seal["signature"] = None
    return seal


def timestamp_seal(seal: dict, pool: tuple[dict, ...] | None = None, transport=None) -> dict:
    """Staple an RFC 3161 timestamp over the seal hash. Unreachable TSAs
    leave `tsa_anchor` None (never raises for that); ACTASEAL_AIRGAPPED
    raises AirgapViolation from the TSA module."""
    from actaseal.anchor.tsa import request_timestamp

    out = copy.deepcopy(seal)
    anchor = request_timestamp(bytes.fromhex(seal_hash(seal)), pool=pool, transport=transport)
    out["tsa_anchor"] = anchor.to_dict() if anchor else None
    return out


def sign_seal(seal: dict, private_key, *, key_id: str) -> dict:
    """Ed25519 signature over SIGNATURE_DOMAIN + the 32-byte seal hash."""
    out = copy.deepcopy(seal)
    digest = bytes.fromhex(seal_hash(seal))
    out["signature"] = {
        "algorithm": "ed25519",
        "key_id": key_id,
        "public_key_hex": private_key.public_key().public_bytes_raw().hex(),
        "signature_hex": private_key.sign(SIGNATURE_DOMAIN + digest).hex(),
    }
    return out


# ---------------------------------------------------------------- verifying

@dataclass
class SealVerification:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_checked: int = 0
    seal_sha256: str | None = None
    timestamp_status: str = TIMESTAMP_MISSING_STATUS
    timestamped_at: str | None = None
    signed_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": "PASS" if self.ok else "FAIL",
            "seal_sha256": self.seal_sha256,
            "files_checked": self.files_checked,
            "failures": self.failures,
            "warnings": self.warnings,
            "timestamp_status": self.timestamp_status,
            "timestamped_at": self.timestamped_at,
            "signed_by": self.signed_by,
        }


def _safe_rel(path: Any) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        return False
    p = PurePosixPath(path)
    return not p.is_absolute() and ".." not in p.parts and ":" not in p.parts[0]


def _well_formed_entry(entry: Any) -> bool:
    return (isinstance(entry, dict) and isinstance(entry.get("sha256"), str) and len(entry["sha256"]) == 64
            and isinstance(entry.get("size"), int) and not isinstance(entry.get("size"), bool))


def _trusted_ca(anchor: dict, tsa_ca_path: str | None) -> str | None:
    if tsa_ca_path:
        return tsa_ca_path
    from actaseal.anchor.tsa import DEFAULT_TSA_POOL, FREETSA_CA_CERT_PATH, FREETSA_CA_CERT_SHA256

    bundled = {m["name"]: m["ca_cert_path"] for m in DEFAULT_TSA_POOL}
    path = bundled.get(anchor.get("tsa_name"))
    if path is None:
        return None
    if (Path(path) == FREETSA_CA_CERT_PATH
            and hashlib.sha256(Path(path).read_bytes()).hexdigest() != FREETSA_CA_CERT_SHA256):
        return None
    return path


def _tsa_gen_time(token_der_hex: str) -> str | None:
    from asn1crypto import cms, tsp  # noqa: F401 -- tsp registers the TSTInfo content type

    try:
        ci = cms.ContentInfo.load(bytes.fromhex(token_der_hex))
        gen_time = ci["content"]["encap_content_info"]["content"].parsed["gen_time"].native
        return gen_time.isoformat()
    except Exception:  # noqa: BLE001 -- informative only; the token was already verified
        return None


def verify_seal(seal: Any, *, base: str | os.PathLike, previous: dict | None = None,
                expected_public_key_hex: str | None = None, tsa_ca_path: str | None = None,
                require_timestamp: bool = False) -> SealVerification:
    if not isinstance(seal, dict) or seal.get("format") != SEAL_FORMAT:
        return SealVerification(ok=False, failures=["SEAL_FORMAT_UNKNOWN"])
    if not isinstance(seal.get("files"), list):
        return SealVerification(ok=False, failures=["SEAL_MALFORMED: files is not a list"])

    result = SealVerification(ok=False)
    digest_hex = seal_hash(seal)
    result.seal_sha256 = digest_hex
    if digest_hex != seal.get("seal_sha256"):
        result.failures.append("SEAL_HASH_MISMATCH")

    # files
    base_abs = os.path.abspath(os.fspath(base))
    for entry in seal["files"]:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not _safe_rel(path):
            result.failures.append(f"SEAL_PATH_INVALID: {path!r}")
            continue
        if not _well_formed_entry(entry):
            result.failures.append(f"SEAL_MALFORMED: {path}")
            continue
        abs_path = os.path.join(base_abs, *PurePosixPath(path).parts)
        if not os.path.isfile(abs_path) or os.path.islink(abs_path):
            result.failures.append(f"FILE_MISSING: {path}")
            continue
        digest, size = _hash_file(abs_path)
        result.files_checked += 1
        if digest != entry["sha256"] or size != entry["size"]:
            result.failures.append(f"FILE_CHANGED: {path}")

    # chain
    if previous is not None:
        try:
            prev_hash = _check_previous(previous)
        except SealError:
            result.failures.append("PREVIOUS_SEAL_INVALID")
        else:
            if seal.get("previous_seal_sha256") != prev_hash:
                result.failures.append("CHAIN_BROKEN")
    elif seal.get("previous_seal_sha256"):
        result.warnings.append("CHAIN_NOT_CHECKED")

    # signature
    sig = seal.get("signature")
    if isinstance(sig, dict):
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pub_hex = str(sig.get("public_key_hex") or "")
        try:
            if sig.get("algorithm") != "ed25519":
                raise ValueError("unsupported algorithm")
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
                bytes.fromhex(str(sig.get("signature_hex") or "")), SIGNATURE_DOMAIN + bytes.fromhex(digest_hex))
            result.signed_by = pub_hex
        except (InvalidSignature, ValueError):
            result.failures.append("SIGNATURE_INVALID")
        if expected_public_key_hex is not None and pub_hex.lower() != expected_public_key_hex.lower():
            result.failures.append("SIGNER_MISMATCH")
        elif expected_public_key_hex is None:
            result.warnings.append("SIGNER_NOT_PINNED")
    elif sig is not None:
        result.failures.append("SIGNATURE_INVALID")
    elif expected_public_key_hex is not None:
        result.failures.append("SIGNATURE_MISSING")

    # timestamp
    raw_anchor = seal.get("tsa_anchor")
    if isinstance(raw_anchor, dict):
        from actaseal.anchor.tsa import TsaAnchor, verify_tsa_token

        ca = _trusted_ca(raw_anchor, tsa_ca_path)
        if ca is None:
            result.timestamp_status = TIMESTAMP_INVALID
            result.failures.append("TSA_CA_UNKNOWN")
        else:
            try:
                anchor = TsaAnchor.from_dict({**raw_anchor, "ca_cert_path": ca})
                ok, reasons = verify_tsa_token(anchor, bytes.fromhex(digest_hex))
            except (KeyError, ValueError) as exc:
                ok, reasons = False, [f"TSA_ANCHOR_MALFORMED: {exc}"]
            if ok:
                result.timestamp_status = TIMESTAMP_OK
                result.timestamped_at = _tsa_gen_time(anchor.token_der_hex)
            else:
                result.timestamp_status = TIMESTAMP_INVALID
                result.failures.append("TSA_INVALID: " + "; ".join(reasons))
    elif raw_anchor is not None:
        result.timestamp_status = TIMESTAMP_INVALID
        result.failures.append("TSA_INVALID: tsa_anchor is not an object")
    elif require_timestamp:
        result.failures.append("TIMESTAMP_MISSING")
    else:
        result.warnings.append("UNTIMESTAMPED")

    result.ok = not result.failures
    return result
