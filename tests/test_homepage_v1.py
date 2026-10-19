"""The homepage is written for a buyer: one headline, one outcome, two ways forward, nothing about how the
product is built, and nothing that belongs to a standards audience.

Two phrases carry product words because they are the names of the actions: the secondary button "Verify a
sample receipt" and the nav entry "Verify a receipt". Everything else on the page keeps the buyer vocabulary.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"
HEADLINE = "When your AI agent moves money and someone disputes it, show proof they can check themselves."
NAV = ["Product", "Verify a receipt", "Paid pilot", "Security", "Contact"]
NAV_HREFS = ["/#product", "https://verify.actaseal.com/browser/", "/pilot/", "/security/", "mailto:sales@actaseal.com"]
ALLOWED_PHRASES = ("Verify a sample receipt", "Verify a receipt")
BUYER_ZONE_BANNED = ("receipt", "signed", "verif", "ledger", "offline", "policy version", "gateway", "tamper",
                     "hash", "ed25519", "docker", "self-hosted", "air-gapped", "open-source", "apache", "api key")
HEADER_PAGES = ["index.html", "as1215/index.html", "changelog/index.html", "docs/index.html", "legal/dpa.html",
                "legal/privacy.html", "legal/subprocessors.html", "legal/terms.html", "trust/index.html"]


def raw() -> str:
    return PAGE.read_text(encoding="utf-8")


def text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def test_the_headline_is_the_agreed_wording_and_the_only_h1():
    assert [text(h) for h in re.findall(r"<h1\b[^>]*>(.*?)</h1>", raw(), flags=re.S)] == [HEADLINE]
    assert HEADLINE in html.unescape(re.search(r"<title>(.*?)</title>", raw(), flags=re.S).group(1)) or "show proof" in raw()


def test_there_is_no_banner_and_no_deadline_on_the_homepage():
    low = raw().lower()
    assert "top-banner" not in low and "pcaob" not in low and "qc 1000" not in low and "verifier live" not in low


def test_one_primary_and_one_secondary_call_in_the_first_section():
    hero = re.search(r'<section id="what">.*?</section>', raw(), flags=re.S).group(0)
    primary = re.search(r'<a class="cta-line" href="(mailto:sales@actaseal\.com[^"]*)">\s*Book a 20-min call\s*</a>', hero)
    secondary = re.search(r'<a class="cta-secondary" href="(https://verify\.actaseal\.com/browser/)">\s*Verify a sample receipt\s*</a>', hero)
    assert primary and secondary
    assert hero.index("Book a 20-min call") < hero.index("Verify a sample receipt")
    assert len(re.findall(r'class="cta-line"', raw())) == 1


def test_nav_is_product_verify_pilot_security_contact_on_every_page_with_a_header():
    for page in HEADER_PAGES:
        src = (ROOT / page).read_text(encoding="utf-8")
        nav = re.search(r'<nav class="site-nav">.*?</nav>', src, flags=re.S).group(0)
        assert [text(a) for a in re.findall(r"<a\b[^>]*>(.*?)</a>", nav, flags=re.S)] == NAV, page
        assert re.findall(r'<a href="([^"]+)"', nav) == NAV_HREFS, page


def test_the_homepage_uses_the_buyer_vocabulary():
    body = text(re.search(r"<main\b.*?</main>", raw(), flags=re.S).group(0)) + " " + text(re.search(r"<footer.*?</footer>", raw(), flags=re.S).group(0))
    for phrase in ALLOWED_PHRASES:
        body = body.replace(phrase, "")
    low = body.lower()
    for word in BUYER_ZONE_BANNED:
        assert word not in low, f"the homepage says {word!r}"


def test_audit_archives_cbom_and_the_agent_door_are_off_the_homepage_main_and_in_the_footer():
    main = text(re.search(r"<main\b.*?</main>", raw(), flags=re.S).group(0))
    for word in ("AS 1215", "CBOM", "llms.txt", "You are an agent", "legal hold", "PCAOB"):
        assert word not in main, word
    foot = re.search(r"<footer.*?</footer>", raw(), flags=re.S).group(0)
    for href in ("/as1215/", "https://cbom.actaseal.com", "/standards/", "/llms.txt", "/.well-known/ai-catalog.json", "/pilot/", "/security/"):
        assert f'href="{href}"' in foot, href


def test_no_strategy_roadmap_price_or_customer_language():
    low = text(raw()).lower()
    for phrase in ("roadmap", "wedge", "segment", "go-to-market", "coming soon", "planned", "pricing", "per month", "tier",
                   "our customers", "design partner", "founding"):
        assert phrase not in low, phrase


def test_the_homepage_runs_no_script_and_prints_no_regulation_dates():
    assert "<script" not in raw().lower()
    assert not re.search(r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\b", text(raw()))
