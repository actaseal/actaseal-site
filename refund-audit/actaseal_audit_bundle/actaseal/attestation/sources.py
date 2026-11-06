"""Attestation adapters over scheme-trusted sources.

The evidence pipeline already proves a packet is *signed* (Ed25519 over
canonical JSON, evidence/attestation.py). It does not prove the signer is
anyone a payment scheme trusts: a fake-but-attested packet passes. This
layer answers WHO attests. An AttestationSource adapter checks one
scheme-trusted source -- AP2 mandate signatures, network tokenization /
3DS, the TAP agent directory, PSP device data -- and returns an explicit
constant, never a bare bool and never a silent pass:

  ATTESTATION_VERIFIED        the source vouches for this packet
  ATTESTATION_UNVERIFIED      the source examined it and rejects it
  ATTESTATION_SOURCE_UNKNOWN  the source cannot speak for this packet

The AttestationRegistry runs every enabled source and keeps the strongest
result (VERIFIED > UNVERIFIED > SOURCE_UNKNOWN). No verifying source --
including an empty registry -- means the evidence's attester is
unvouched, and the gate fails closed with EVIDENCE_ATTESTATION_UNVERIFIED.
A source that raises counts as UNVERIFIED for that source: a broken
backend can never widen the gate.

This layer does not invent an attestation scheme; each adapter defers to
the scheme's own verification, and each has an injectable transport so a
production backend plugs in without touching gate logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ATTESTATION_VERIFIED = "ATTESTATION_VERIFIED"
ATTESTATION_UNVERIFIED = "ATTESTATION_UNVERIFIED"
ATTESTATION_SOURCE_UNKNOWN = "ATTESTATION_SOURCE_UNKNOWN"

ATTESTATION_RESULTS = (ATTESTATION_VERIFIED, ATTESTATION_UNVERIFIED, ATTESTATION_SOURCE_UNKNOWN)

# Gate reason code: no enabled source vouched for the evidence's attester.
EVIDENCE_ATTESTATION_UNVERIFIED = "EVIDENCE_ATTESTATION_UNVERIFIED"

# source_id reported when there was no source to consult at all.
NO_ATTESTATION_SOURCE = "no_attestation_source"

# Strongest first. A registry's answer is the best any source could do.
_STRENGTH = {
    ATTESTATION_VERIFIED: 2,
    ATTESTATION_UNVERIFIED: 1,
    ATTESTATION_SOURCE_UNKNOWN: 0,
}


@dataclass(frozen=True)
class AttestationResult:
    result: str
    source_id: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.result not in ATTESTATION_RESULTS:
            raise ValueError(f"attestation result must be one of {ATTESTATION_RESULTS}: {self.result!r}")


class AttestationSource(Protocol):
    """One scheme-trusted source. verify() must return an AttestationResult
    carrying one of the explicit constants -- never a bool, never None."""

    source_id: str

    def verify(self, evidence) -> AttestationResult: ...


class AttestationRegistry:
    def __init__(self, *, sources: tuple[AttestationSource, ...]) -> None:
        self._sources = tuple(sources)

    def verify_each(self, evidence) -> tuple[AttestationResult, ...]:
        """One result per enabled source, in registration order. A raising
        source yields UNVERIFIED for that source -- fail closed, no escape."""
        results: list[AttestationResult] = []
        for source in self._sources:
            try:
                result = source.verify(evidence)
            except Exception as exc:
                result = AttestationResult(
                    result=ATTESTATION_UNVERIFIED,
                    source_id=getattr(source, "source_id", "unknown_source"),
                    detail=f"source raised: {exc}",
                )
            results.append(result)
        return tuple(results)

    def verify(self, evidence) -> AttestationResult:
        """The strongest result any enabled source produced. An empty
        registry answers SOURCE_UNKNOWN: nothing vouched."""
        results = self.verify_each(evidence)
        if not results:
            return AttestationResult(
                result=ATTESTATION_SOURCE_UNKNOWN,
                source_id=NO_ATTESTATION_SOURCE,
                detail="no attestation sources enabled",
            )
        return max(results, key=lambda result: _STRENGTH[result.result])


# ONESHOT-BUCKET1 Task 1: this registry existed, was tested, and was
# never constructed by any real bootstrap path -- GatewayRuntimeConfig.
# attestation_registry defaulted to None everywhere, so
# EVIDENCE_ATTESTATION_UNVERIFIED never engaged in any running server.
# build_default_attestation_registry is the one place that turns "four
# tested adapter classes" into "a real, populated registry a deployment
# actually uses" -- every real caller (actaseal.api.server's PRODUCTION
# bootstrap, demo/ui_demo.py) goes through this, not its own ad hoc
# construction.
DEFAULT_DISABLED_SOURCES: frozenset[str] = frozenset()

ALL_SOURCE_IDS = ("ap2_mandate_signature", "network_token", "psp_device", "tap_agent_directory")


def _dev_only_ap2_public_key():
    """A deployment that hasn't configured a real AP2 issuer public key
    (via ACTASEAL_AP2_ATTESTATION_PUBLIC_KEY_HEX) still gets the source
    CONSTRUCTED (never silently missing from the registry -- see the
    module-level docstring on why "absent" and "present but never
    matches anything real" are different, and this bootstrap always
    prefers the latter unless a source is explicitly disabled), keyed to
    a fresh, random, throwaway keypair generated at process start. No
    real AP2 mandate will ever verify against it -- that is the point:
    it is honestly unable to vouch for anything until a real issuer key
    is configured, exactly the same SOURCE_UNKNOWN/UNVERIFIED posture an
    unconfigured network_token/psp_device/tap_directory source already
    has by default."""
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.generate_private_key(ec.SECP256R1()).public_key()


def ap2_public_key_from_hex(hex_value: str):
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(hex_value))


def ap2_public_key_to_hex(public_key) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint).hex()


def build_default_attestation_registry(
    *,
    ap2_public_key_hex: str | None = None,
    ap2_mandate_records: dict[str, dict] | None = None,
    network_token_records: dict[str, dict] | None = None,
    psp_device_records: dict[str, dict] | None = None,
    tap_directory_records: dict[str, dict] | None = None,
    disabled_sources: frozenset[str] = DEFAULT_DISABLED_SOURCES,
) -> AttestationRegistry:
    """The real, default 4-source registry. Every source is CONSTRUCTED
    by default -- "configurable and able to be absent" means each
    source's own backing data is configurable (the *_records dicts, or
    a real ap2_public_key_hex) and each can be explicitly turned off via
    `disabled_sources`, never that the registry silently ends up with
    zero sources because nothing was configured. An unconfigured source
    (empty records / the dev-only throwaway AP2 key) reports
    SOURCE_UNKNOWN/UNVERIFIED for everything it's asked about -- honest,
    fail-closed, never a silent pass -- exactly the posture each
    source's own module docstring already describes for its "no
    production backend wired" default."""
    from actaseal.attestation.network_token import InMemoryNetworkTokenRecords, NetworkTokenSource
    from actaseal.attestation.psp_device import InMemoryPspDeviceRecords, PspDeviceDataSource
    from actaseal.attestation.tap_directory import InMemoryTapAgentDirectory, TapAgentDirectorySource

    sources: list[AttestationSource] = []

    if "ap2_mandate_signature" not in disabled_sources:
        from actaseal.attestation.ap2_source import Ap2MandateSignatureSource, InMemoryMandateStore

        public_key = ap2_public_key_from_hex(ap2_public_key_hex) if ap2_public_key_hex else _dev_only_ap2_public_key()
        sources.append(
            Ap2MandateSignatureSource(
                public_key=public_key,
                mandate_resolver=InMemoryMandateStore(ap2_mandate_records),
            )
        )

    if "network_token" not in disabled_sources:
        sources.append(NetworkTokenSource(token_lookup=InMemoryNetworkTokenRecords(network_token_records)))

    if "psp_device" not in disabled_sources:
        sources.append(PspDeviceDataSource(device_data_lookup=InMemoryPspDeviceRecords(psp_device_records)))

    if "tap_agent_directory" not in disabled_sources:
        sources.append(
            TapAgentDirectorySource(directory_lookup=InMemoryTapAgentDirectory(tap_directory_records))
        )

    return AttestationRegistry(sources=tuple(sources))
