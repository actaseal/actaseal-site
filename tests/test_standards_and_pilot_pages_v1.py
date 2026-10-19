"""What left the homepage lives on its own pages: the standards and open-source page carries the proof, the
open-source terms and the audit-archive use; the paid-pilot page says what a pilot is without a price."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    raw = (ROOT / rel).read_text(encoding="utf-8")
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def test_the_standards_page_keeps_the_proof_list_the_open_terms_and_the_two_proof_lines():
    raw = (ROOT / "standards/index.html").read_text(encoding="utf-8")
    for url in ("https://datatracker.ietf.org/doc/draft-xg-payment-dispute-profile/", "https://doi.org/10.5281/zenodo.23309307",
                "https://pypi.org/project/actaseal-verify/", "https://github.com/actaseal/x402-acceptance-check-cold",
                "https://github.com/actaseal/actaseal-verify"):
        assert url in raw, url
    t = text("standards/index.html")
    assert "Independent implementations" in t and "all 50 vectors" in t and "6e487f0" in t
    assert "The verifier and the evidence pack format are free and open under the Apache License 2.0" in t
    assert "Your proof still verifies if we disappear." in t
    assert "Records live outside the agent, so a compromised agent cannot rewrite them." in t
    assert "PCAOB AS 1215" in t and "not certified under any of them" in t
    assert 'href="/limits/"' in raw


def test_the_pilot_page_says_what_a_pilot_is_and_names_no_price_or_term():
    t = text("pilot/index.html")
    low = t.lower()
    assert "paid pilot" in low and "Book a 20-min call" in t
    for word in ("$", "€", "£", "₹", "per month", "per year", "tier", "discount", "pricing", "free"):
        assert word not in low, word
    raw = (ROOT / "pilot/index.html").read_text(encoding="utf-8")
    assert 'href="mailto:sales@actaseal.com' in raw


def test_both_pages_carry_the_site_header_and_nav():
    for rel in ("standards/index.html", "pilot/index.html"):
        raw = (ROOT / rel).read_text(encoding="utf-8")
        assert '<header class="site-head">' in raw and 'rel="apple-touch-icon"' in raw, rel
