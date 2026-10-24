"""The booking call opens the calendar, the same link on the homepage and the pilot page. Contact stays a mail link."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = "https://cal.com/actaseal/20min"


def test_both_pages_book_through_the_calendar_and_no_booking_link_is_a_mail():
    for page in (ROOT / "index.html", ROOT / "pilot" / "index.html"):
        src = page.read_text(encoding="utf-8")
        hrefs = re.findall(r'href="([^"]*)"[^>]*>\s*Book a 20-min call', src)
        assert hrefs and set(hrefs) == {CAL}, page


def test_sales_mail_is_still_on_the_homepage():
    # The nav books a call; the footer keeps the mail address for anyone who would rather write.
    assert 'href="mailto:sales@actaseal.com">sales@actaseal.com</a>' in (ROOT / "index.html").read_text(encoding="utf-8")
