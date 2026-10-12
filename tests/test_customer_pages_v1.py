"""Two things a buyer's security review asks for in writing: what happens
if a signing key is compromised, and what can and cannot be deleted.

Both pages state product behaviour, so the facts that can drift are
checked against the product when it is checked out next to this site.
"""
import datetime
import html
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = Path.home() / "a/active_code"
KEY_PAGE = ROOT / "security" / "key-compromise" / "index.html"
DELETION_PAGE = ROOT / "trust" / "retention-and-deletion" / "index.html"
SECURITY = ROOT / "security" / "index.html"
TRUST = ROOT / "trust" / "index.html"
SECURITY_TXT = ROOT / ".well-known" / "security.txt"


def _text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def test_both_pages_are_published():
    assert KEY_PAGE.is_file() and DELETION_PAGE.is_file()


@pytest.mark.parametrize("page", [KEY_PAGE, DELETION_PAGE], ids=["key-compromise", "retention-and-deletion"])
def test_pages_carry_no_internal_references(page):
    text = _text(page)
    for pattern in (r"\bdocs/", r"\.py\b", r"\.md\b", r"runbook", r"ProofLedger", r"actaseal[./]\w+[./]", r"data_map"):
        assert not re.search(pattern, text), f"{page.parent.name}: internal reference matching {pattern!r}"


def test_key_compromise_page_says_what_happens_to_existing_receipts():
    text = _text(KEY_PAGE)
    assert "security@actaseal.com" in text
    for phrase in ("revoked", "stays listed", "new key", "timestamp", "before the compromise"):
        assert phrase in text, phrase
    assert "/.well-known/actaseal-keys.json" in text


def test_deletion_page_says_what_can_and_cannot_be_erased():
    text = _text(DELETION_PAGE)
    for phrase in (
        "can be erased", "cannot be erased", "legal hold", "IP address", "device fingerprint", "email address",
        "shipping address", "order", "payment", "approver", "7 years",
    ):
        assert phrase.lower() in text.lower(), phrase


def test_deletion_facts_match_the_product():
    profile = PRODUCT / "actaseal/archive/retention_profile.py"
    context = PRODUCT / "actaseal/dispute/dispute_context.py"
    shred = PRODUCT / "actaseal/privacy/shred.py"
    if not (profile.is_file() and context.is_file() and shred.is_file()):
        pytest.skip("product repository is not checked out next to this one")
    assert 'name="pcaob", documentation_completion_window_days=14, workpaper_retention_years=7' in profile.read_text()
    assert "workpaper_retention_years=5" in profile.read_text()
    fields = re.search(r"_PII_FIELDS = \((.*?)\)", context.read_text(), flags=re.S).group(1)
    assert set(re.findall(r'"(\w+)"', fields)) == {
        "customer_purchase_ip", "customer_device_fingerprint", "customer_device_id",
        "customer_email_address", "shipping_address", "customer_account_id",
    }, "the list of erasable fields changed: update the deletion page"
    assert "LEGAL_HOLD_SHRED_REFUSED" in shred.read_text()


def test_security_and_trust_link_to_both_pages():
    for page in (SECURITY, TRUST):
        raw = page.read_text(encoding="utf-8")
        assert 'href="/security/key-compromise/"' in raw, f"{page.parent.name}: no link to the key-compromise page"
        assert 'href="/trust/retention-and-deletion/"' in raw, f"{page.parent.name}: no link to the deletion page"


def test_trust_page_states_deletion_in_brief():
    raw = TRUST.read_text(encoding="utf-8")
    section = re.search(r'<section id="deletion">.*?</section>', raw, flags=re.S)
    assert section, "trust page has no deletion statement"
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", section.group(0))))
    assert "destroying" in text and "key" in text
    assert "cannot be erased" in text
    assert "legal hold" in text.lower()


def test_trust_renderer_keeps_the_deletion_statement_and_links(tmp_path):
    out = tmp_path / "trust.html"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "render_trust_page.py"),
         str(ROOT / "tests" / "fixtures" / "trust_bundle_sample.json"), str(out)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    page = out.read_text()
    assert '<section id="deletion">' in page
    assert 'href="/security/key-compromise/"' in page and 'href="/trust/retention-and-deletion/"' in page


def test_security_txt_contact_is_the_security_address_only_and_not_expired():
    lines = SECURITY_TXT.read_text(encoding="utf-8").splitlines()
    contacts = [line.split(":", 1)[1].strip() for line in lines if line.startswith("Contact:")]
    assert contacts == ["mailto:security@actaseal.com"]
    assert "sales@" not in SECURITY_TXT.read_text(encoding="utf-8")
    expires = [line.split(":", 1)[1].strip() for line in lines if line.startswith("Expires:")]
    assert len(expires) == 1
    when = datetime.datetime.fromisoformat(expires[0].replace("Z", "+00:00"))
    assert when > datetime.datetime.now(datetime.timezone.utc), "security.txt has expired"
