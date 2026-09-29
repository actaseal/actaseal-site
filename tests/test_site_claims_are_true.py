"""Every factual claim this site makes, checked against the product.

Same rule as actaseal-verify's test_claims_are_true.py: any claim that can
drift MUST get a test here. If you cannot write the test, you may not make
the claim on a public page.

The product repo is not present on every machine. Where a check needs it,
the test returns rather than failing, so this file stays useful in a
site-only checkout.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCT = Path.home() / "a/active_code"
VERIFY = Path.home() / "a/actaseal-verify"


def pages():
    return {
        str(p.relative_to(REPO_ROOT)): p.read_text(encoding="utf-8")
        for p in REPO_ROOT.rglob("*.html")
        if ".git" not in p.parts and "tests" not in p.parts
    }


def product_text():
    if not PRODUCT.exists():
        return None
    out = []
    for p in (PRODUCT / "actaseal").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        out.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(out)


# --- claims about what the product does -------------------------------


def test_named_routes_exist():
    """as1215/ names specific routes. Each must exist in the product."""
    src = product_text()
    if src is None:
        return
    claimed = {
        "post-archive-addition": "post-archive-addition",
        "inspection-pack": "inspection-pack",
        "fre902-certification-package": "fre902-certification-package",
        "gateway/preflight": "/gateway/preflight",
    }
    for page, t in pages().items():
        for needle, route in claimed.items():
            if needle in t:
                assert route in src, f"{page}: names route {route!r}, not in product"


def test_clock_trust_claim_has_an_implementation():
    """The claim that the archive lock does not rest on the local clock."""
    if not PRODUCT.exists():
        return
    for page, t in pages().items():
        if "RFC 3161" in t or "local clock" in t:
            assert (PRODUCT / "actaseal/archive/clock_trust.py").exists(), \
                f"{page}: claims external clock trust, clock_trust.py missing"
            assert (PRODUCT / "actaseal/anchor/tsa.py").exists(), \
                f"{page}: claims RFC 3161 anchoring, anchor/tsa.py missing"


def test_workpaper_identity_claim():
    if not PRODUCT.exists():
        return
    for page, t in pages().items():
        if "EQR" in t:
            assert (PRODUCT / "actaseal/archive/workpaper_identity.py").exists(), \
                f"{page}: claims per-workpaper preparer/reviewer/EQR identity, module missing"


def test_terms_hash_is_actually_bound_into_the_receipt():
    """The landing page shows a receipt carrying terms_hash."""
    src = product_text()
    if src is None:
        return
    for page, t in pages().items():
        if "terms_hash" in t:
            assert "terms_hash=terms_hash" in src, \
                f"{page}: shows terms_hash in a receipt, but nothing binds it"


# Names the CALLER chooses in their own application, not env vars the
# product reads. The SDK takes these as constructor options.
CALLER_CHOSEN_ENV = {"ACTASEAL_API_KEY"}


def test_named_env_vars_exist():
    """privacy.html and the quickstart enumerate env vars the product reads.
    A renamed variable makes those pages wrong."""
    src = product_text()
    if src is None:
        return
    for page, t in pages().items():
        for var in re.findall(r"ACTASEAL_[A-Z_]+", t):
            if var in CALLER_CHOSEN_ENV:
                continue
            assert var in src, f"{page}: names {var}, which the product does not define"


def test_no_installable_claim_for_an_unpublished_package():
    """The docs show a TypeScript import. Every package.json for it is
    marked private, so it is not installable from npm. The page must say
    so, and this test breaks the moment either fact changes."""
    import json
    if not PRODUCT.exists():
        return
    manifests = [PRODUCT / "packages/actaseal-sdk-ts/package.json",
                 PRODUCT / "sdk-ts/package.json"]
    present = [m for m in manifests if m.exists()]
    if not present:
        return
    all_private = all(
        json.loads(m.read_text(encoding="utf-8")).get("private") is True
        for m in present
    )
    docs = REPO_ROOT / "docs/index.html"
    if not docs.exists():
        return
    t = docs.read_text(encoding="utf-8")
    if "@actaseal/sdk" not in t:
        return
    if all_private:
        assert "not published to npm" in t, (
            "docs/index.html shows an @actaseal/sdk import while every "
            "package.json for it is private: say it is not on npm")
    else:
        assert "not published to npm" not in t, (
            "a package.json is no longer private: the docs still claim the "
            "SDK is not on npm. Publish it or restore private: true")


def test_usage_export_guard_test_still_exists():
    """privacy.html cites a specific test as the enforcement for
    'counts only'. If that test is deleted, the claim is unsupported."""
    if not PRODUCT.exists():
        return
    cited = "tests/test_usage_export_no_payload_fields_v1.py"
    for page, t in pages().items():
        if cited in t:
            assert (PRODUCT / cited).exists(), \
                f"{page}: cites {cited}, which no longer exists"


def test_verifier_is_apache_licensed_and_separate():
    if not VERIFY.exists():
        return
    lic = VERIFY / "LICENSE"
    for page, t in pages().items():
        if "Apache License 2.0" in t or "Apache-2.0" in t:
            assert lic.exists(), f"{page}: claims an Apache-2.0 verifier, no LICENSE file"
            assert "Apache License" in lic.read_text(encoding="utf-8"), \
                f"{page}: claims Apache-2.0, LICENSE says otherwise"


# --- claims about what the product does NOT do ------------------------


def test_no_unwired_capability_words():
    """Mirrors the verify repo's banned list. ops/continuity_monitor.py's
    periodic check and alerting were never wired."""
    banned = ("alerting", "real-time monitoring", "continuous monitoring",
              "unphishable", "WYSIWYS")
    for page, t in pages().items():
        low = t.lower()
        for w in banned:
            assert w.lower() not in low, f"{page}: claims {w!r}, which is not implemented"


def test_no_soc2_certification_claim():
    for page, t in pages().items():
        low = t.lower()
        for phrase in ("soc 2 certified", "soc 2 compliant", "soc2 certified",
                       "soc 2 attested", "soc 2 type ii report available"):
            assert phrase not in low, f"{page}: claims {phrase!r}, which is not true"


def test_no_regulator_endorsement_claim():
    for page, t in pages().items():
        low = t.lower()
        for phrase in ("pcaob approved", "pcaob-approved", "pcaob endorsed",
                       "approved by the pcaob", "certified by the pcaob"):
            assert phrase not in low, f"{page}: claims a regulator endorsement that does not exist"


def test_no_private_repo_citations():
    for page, t in pages().items():
        assert "private repo" not in t.lower(), f"{page}: cites a repo nobody can open"


def test_no_third_party_assets_loaded():
    """privacy.html says this site loads no third-party assets. Anchors to
    other sites are fine; loading a script, stylesheet, image, font or frame
    from one is not."""
    allowed = ("actaseal.com", "verify.actaseal.com")
    pattern = re.compile(
        r'<(?:script|img|iframe|source|embed)\b[^>]*\bsrc\s*=\s*["\']([^"\']+)'
        r'|<link\b[^>]*\bhref\s*=\s*["\']([^"\']+)',
        re.I,
    )
    for page, t in pages().items():
        for m in pattern.finditer(t):
            url = m.group(1) or m.group(2)
            if not url.lower().startswith(("http://", "https://", "//")):
                continue
            host = re.sub(r"^(?:https?:)?//", "", url).split("/")[0].lower()
            assert any(host == a or host.endswith("." + a) for a in allowed), \
                f"{page}: loads a third-party asset from {host}, contradicting privacy.html"


def test_subprocessor_list_claims_to_be_complete_and_no_others_appear():
    """subprocessors.html says the list is complete. Cross-check that no
    other vendor's asset host shows up anywhere in the site."""
    subs = REPO_ROOT / "legal/subprocessors.html"
    if not subs.exists():
        return
    t = subs.read_text(encoding="utf-8")
    for name in ("Paddle", "Zoho", "GitHub", "Spaceship"):
        assert name in t, f"subprocessors.html no longer lists {name}"
    for vendor in ("google-analytics", "googletagmanager", "hotjar", "segment.com",
                   "intercom", "hubspot", "mixpanel", "plausible", "fonts.googleapis"):
        for page, pt in pages().items():
            assert vendor not in pt.lower(), \
                f"{page}: references {vendor}, which is not on the sub-processor list"
