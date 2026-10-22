"""ONE-SHOT 6B H16: until there is a calendar, the booking CTA is a mailto: link. It must open a message that already
says what it is, with the questions that make the reply useful, and the whole thing must survive being URL-encoded."""
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def _booking_links():
    found = []
    for page in (ROOT / "index.html", ROOT / "pilot" / "index.html"):
        for href in re.findall(r'href="(mailto:[^"]*)"[^>]*>\s*Book a 20-min call', page.read_text(encoding="utf-8")):
            found.append((page.name, href))
    return [(n, h.replace("&amp;", "&")) for n, h in found]


def test_both_pages_have_the_booking_link():
    assert len(_booking_links()) == 2


def test_the_mail_opens_with_a_subject_and_a_body_that_asks_for_what_the_reply_needs():
    for name, href in _booking_links():
        parts = urlsplit(href)
        assert parts.path == "sales@actaseal.com"
        q = parse_qs(parts.query, keep_blank_values=True)
        assert q["subject"] == ["ActaSeal 20-min call"], name
        body = q["body"][0]
        for question in ("Your name and company", "Two or three times that suit you", "time zone", "agent", "What you want to see"):
            assert question.lower() in body.lower(), (name, question)
        assert "\n" in body
        assert " " not in href and "\n" not in href, name
