"""The Colorado SB 26-189 note says what it was given to say, matches the dates tracker's verified row,
uses no product vocabulary and carries no call to action."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "notes" / "colorado-sb-26-189.html"
TRACKER = Path.home() / "a/active_code/docs/internal/regulatory_dates.md"
SOURCES = ("https://leg.colorado.gov/bills/sb26-189",
           "https://www.seyfarth.com/news-insights/colorado-enacts-artificial-intelligence-replacement-law.html")

REQUIRED = [
    "Colorado SB 26-189: can you show what happened, three years later?",
    "Colorado's SB 26-189 replaced its AI Act. Its main obligations are reported to apply from 1 January 2027.",
    "If an automated system materially influences a decision about lending, insurance, housing, employment, "
    "healthcare, education or public services, the people affected get notice, an explanation and a right to "
    "human review, and records have to be kept for three years.",
    "So the question for any team using AI in those decisions is simple: if a customer asks why the system said "
    "no, can you show them what actually happened, three years later?",
    "This is a reading of public summaries of the law, not legal advice.",
    "Sources: Colorado General Assembly, SB26-189, https://leg.colorado.gov/bills/sb26-189 ; Seyfarth Shaw, "
    "https://www.seyfarth.com/news-insights/colorado-enacts-artificial-intelligence-replacement-law.html",
]
FORBIDDEN = ("receipt", "signed", "verif", "ledger", "offline", "policy", "attest", "evidence pack")


def _read():
    raw = NOTE.read_text(encoding="utf-8")
    body = re.search(r"<article>.*?</article>", raw, re.S).group(0)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip(), raw


def test_the_note_says_exactly_what_it_was_given_to_say():
    text, _ = _read()
    for piece in REQUIRED:
        assert piece in text, piece


def test_it_is_a_note_like_the_others_and_links_both_sources():
    _, raw = _read()
    assert re.search(r'<time datetime="2026-10-19">19 October 2026</time> &middot; Xavier Goshi &middot; Last reviewed: '
                     r'<time class="reviewed" datetime="2026-10-19">19 October 2026</time>', raw)
    for url in SOURCES:
        assert f'<a href="{url}">' in raw, url


def test_no_product_vocabulary_and_no_call_to_action():
    text, raw = _read()
    meta = " ".join(re.findall(r'<meta (?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)" content="(.*?)">', raw))
    title = re.search(r"<title>(.*?)</title>", raw).group(1).replace("&middot; ActaSeal", "")
    low = f"{text} {meta} {title}".lower()
    for word in FORBIDDEN:
        assert word not in low, word
    assert "mailto:" not in raw and "book a demo" not in raw.lower() and "pip install" not in raw


def test_its_facts_match_the_dates_tracker_row():
    if not TRACKER.exists():
        return
    row = next(l for l in TRACKER.read_text(encoding="utf-8").splitlines() if l.startswith("| Colorado AI Act"))
    assert "SB 26-189" in row and "1 January 2027" in row and "VERIFIED" in row
    assert "three-year record keeping" in row and "notice, explanation and human-review" in row
