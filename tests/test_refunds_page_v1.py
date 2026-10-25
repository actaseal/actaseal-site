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
