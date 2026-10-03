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


# --- path/attribution hygiene -------------------------------------------


# Every repo path cited inside a <code>...</code> span on this site,
# verified to exist in the product repo (~/a/active_code) as of this
# commit. A path that stops existing (a rename, a delete) must be fixed
# here in the SAME change that fixes the page -- this list is not a
# rubber stamp, it is the actual set of paths this commit checked.
# The product repository is private, so the public site cites none.
CITED_REPO_PATHS: set[str] = set()

# A cited string counts as a "repo path" if it contains a "/" AND either
# ends in one of these file extensions or ends in "/" (a directory).
# This deliberately excludes HTTP routes -- both the plain kind (e.g.
# "/gateway/preflight", "GET /readyz", covered by test_named_routes_exist
# instead) and served-but-not-a-file endpoints that happen to end in one
# of these extensions (e.g. "/.well-known/actaseal-keys.json", which
# GET /.well-known/actaseal-keys.json computes at request time, not a
# path on disk). A leading "/" is the signal: every real repo-relative
# path cited on this site is relative (no leading slash); a route always
# has one.
_PATH_EXTENSIONS = (".py", ".sh", ".json", ".ts", ".md")


def _looks_like_repo_path(text: str) -> bool:
    if "/" not in text or text.startswith("/"):
        return False
    return text.endswith("/") or text.endswith(_PATH_EXTENSIONS)


def test_cited_repo_paths_are_not_stale():
    """Every <code>...</code> span that looks like a repo path must be in
    the explicit CITED_REPO_PATHS allowlist, and (where the product repo
    is present) every allowlisted path must actually exist. A path that
    isn't in the allowlist is either a typo or a citation nobody vetted
    -- both are fail-closed here."""
    code_pattern = re.compile(r"<code>([^<]*)</code>")
    found = set()
    for page, t in pages().items():
        for m in code_pattern.finditer(t):
            candidate = m.group(1).strip()
            if _looks_like_repo_path(candidate):
                found.add(candidate)
                assert candidate in CITED_REPO_PATHS, (
                    f"{page}: cites path {candidate!r} inside <code>, "
                    f"not in the CITED_REPO_PATHS allowlist"
                )
    unused = CITED_REPO_PATHS - found
    assert not unused, f"CITED_REPO_PATHS has entries no page cites: {unused}"

    if not PRODUCT.exists():
        return
    for path in CITED_REPO_PATHS:
        assert (PRODUCT / path).exists(), \
            f"CITED_REPO_PATHS lists {path!r}, which does not exist in the product repo"


# Item numbers (issue/PR numbers on ietf-wg-scitt/draft-ietf-scitt-
# architecture) that ActaSeal itself actually authored/filed. Only
# these may be described with a "filed by ActaSeal"/"filed by us"
# style phrase. #462 was opened by maxchop; #463 is an ActaSeal PR
# against someone else's issue, described as a contribution, not a
# filing, so neither belongs here.
ACTASEAL_AUTHORED = {"461"}

_ATTRIBUTION_PHRASES = ("filed by actaseal", "filed by us")
_ITEM_NUMBER_RE = re.compile(r"#(\d+)")


def test_attribution_claims_are_explicit():
    """'filed by ActaSeal'/'filed by us' must only appear attached to an
    item number in ACTASEAL_AUTHORED. Scoped to the SCITT architecture
    proof-list line (one <li> per item): finds every <li> containing an
    attribution phrase and checks every #NNN item number mentioned in
    that same <li> is one ActaSeal actually filed."""
    li_pattern = re.compile(r"<li>.*?</li>", re.I | re.S)
    for page, t in pages().items():
        for li_match in li_pattern.finditer(t):
            li = li_match.group(0)
            low = li.lower()
            if not any(phrase in low for phrase in _ATTRIBUTION_PHRASES):
                continue
            numbers = _ITEM_NUMBER_RE.findall(li)
            assert numbers, (
                f"{page}: has a 'filed by' attribution with no #NNN item "
                f"number to check it against: {li!r}"
            )
            for number in numbers:
                assert number in ACTASEAL_AUTHORED, (
                    f"{page}: claims item #{number} was 'filed by' ActaSeal, "
                    f"but #{number} is not in ACTASEAL_AUTHORED"
                )


def test_sample_pack_sha256_matches_the_published_files():
    """sample/index.html prints a SHA-256 for each of the two sample
    inspection pack zips. Same drift guard as every other claim in this
    file: the printed hash must match the real file's hash, both
    directions (a stale page claim, or a swapped-in file, both fail)."""
    import hashlib

    page = (REPO_ROOT / "sample" / "index.html").read_text(encoding="utf-8")
    for filename in ("sample-inspection-pack.zip", "sample-inspection-pack-tampered.zip"):
        file_path = REPO_ROOT / "sample" / filename
        assert file_path.is_file(), f"{filename} is referenced by sample/index.html but does not exist"
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        # Scoped to the file-hashes table row specifically (not just "any
        # 64-hex string somewhere after this filename in the page") -- the
        # page also prints an unrelated 64-hex public key in its verify
        # commands, which a looser pattern could mistake for the hash.
        row_pattern = re.compile(
            r"<code>" + re.escape(filename) + r"</code></td><td class=\"hash\">([0-9a-f]{64})</td>"
        )
        match = row_pattern.search(page)
        assert match, f"could not find {filename}'s row in sample/index.html's SHA-256 table"
        assert match.group(1) == actual, (
            f"sample/index.html's SHA-256 for {filename} is {match.group(1)}, "
            f"but the real file hashes to {actual}"
        )
