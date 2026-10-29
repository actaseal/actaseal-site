"""The refund audit page speaks to a support or finance lead, names no price or term, books
through the calendar, and carries the site's header."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / "refunds" / "index.html").read_text(encoding="utf-8")
TEXT = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", RAW))).lower()


def test_names_no_price_term_or_discount():
    for word in ("$", "€", "£", "₹", "inr ", "usd ", "per month", "per year", "discount", "free", "pricing"):
        assert word not in TEXT, word


def test_books_through_the_calendar_and_keeps_a_mail_address():
    assert RAW.count('href="https://cal.com/actaseal/20min"') >= 2
    assert 'href="mailto:sales@actaseal.com"' in RAW


def test_states_no_system_access_and_what_is_found():
    assert "nothing connects to your systems" in TEXT
    for finding in ("same order", "more than the order was worth", "again and again"):
        assert finding in TEXT, finding


def test_has_the_site_header_and_is_in_the_sitemap():
    assert '<nav class="site-nav">' in RAW
    assert "https://actaseal.com/refunds/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_says_what_it_needs_from_the_export_and_that_any_layout_works():
    need = re.search(r'<section id="refunds-need">.*?</section>', RAW, re.S)
    assert need, "no 'what we need' section"
    low = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", need.group(0)))).lower()
    for item in ("amount", "currency", "order", "customer", "approved", "your own column names"):
        assert item in low, item


def test_says_what_happens_to_the_file():
    for phrase in ("only under a signed nda", "never connected", "deleted"):
        assert phrase in TEXT, phrase


def test_shows_an_example_report_page_marked_as_made_up():
    img = re.search(r'<img[^>]+src="/refunds/example-report-page-1\.png"[^>]*>', RAW)
    assert img and "made-up" in img.group(0).lower()
    assert (ROOT / "refunds" / "example-report-page-1.png").is_file()


def test_tells_the_reader_where_their_security_team_goes():
    main = re.search(r"<main\b.*?</main>", RAW, re.S).group(0)
    assert 'href="/security/"' in main


def test_the_pilot_page_hands_the_security_review_its_page():
    pilot = (ROOT / "pilot" / "index.html").read_text(encoding="utf-8")
    main = re.search(r"<main\b.*?</main>", pilot, re.S).group(0)
    assert 'href="/security/"' in main and "security team" in main.lower()
