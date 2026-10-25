"""Two notes added 2026-10-25: the EU AI Act's high-risk deadline moving, and EMVCo's draft agentic
payments framework. Each says what its sources say and no more, asks the question, carries no
product vocabulary or call to action, and is signed ActaSeal rather than with a person's name."""
import html
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("receipt", "signed", "verif", "ledger", "offline", "policy", "attest", "evidence pack", "tamper",
             "gateway", "actaseal can", "we can", "our product")

NOTES = {
    "eu-ai-act-high-risk-deadline-moved.html": {
        "level": "2", "source_date": "2026-07-24",
        "required": [
            "EU AI Act: the high-risk deadline moved. The logs question did not.",
            "The Digital Omnibus on AI was published in the Official Journal on 24 July 2026 and entered into force "
            "on 27 July 2026.",
            "from 2 August 2026 to 2 December 2027",
            "2 August 2028",
            "at least six months",
            "This is a reading of the regulation and of public summaries of it, not legal advice.",
        ],
        "links": ["https://www.lewissilkin.com/insights/2026/07/27/the-digital-omnibus-on-ai-enters-into-force-today-102nedo",
                  "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"],
    },
    "emvco-agentic-payments-framework.html": {
        "level": "1", "source_date": "2026-09-01",
        "required": [
            "EMVCo's agentic payments draft: who shows what the agent did with the customer's intent?",
            "On 1 September 2026 EMVCo asked for public feedback, until 30 September, on a draft",
            "EMV Agentic Payments – Framework for Specifications",
            "The announcement does not mention disputes or liability.",
            "This is a reading of EMVCo's announcement, not legal advice.",
        ],
        "links": ["https://www.ansa.it/sito/notizie/economia/business_wire/2026/09/01/emvco-requests-feedback-on-framework-for-secure-interoperable-and-scalable-card_d1aa8cc6-6678-4d51-9daf-a56be16355bb.html"],
    },
}


def _read(name):
    raw = (ROOT / "notes" / name).read_text(encoding="utf-8")
    body = re.search(r"<article>.*?</article>", raw, re.S).group(0)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip(), raw


@pytest.mark.parametrize("name", NOTES)
def test_the_note_says_what_its_sources_say(name):
    text, raw = _read(name)
    for piece in NOTES[name]["required"]:
        assert piece in text, piece
    for link in NOTES[name]["links"]:
        assert f'<a href="{link}">' in raw, link


@pytest.mark.parametrize("name", NOTES)
def test_level_source_date_and_byline(name):
    _, raw = _read(name)
    assert f'<meta name="actaseal:criticality" content="{NOTES[name]["level"]}">' in raw
    assert f'<meta name="actaseal:source-date" content="{NOTES[name]["source_date"]}">' in raw
    assert "&middot; ActaSeal &middot; Last reviewed:" in raw and "Goshi" not in raw


@pytest.mark.parametrize("name", NOTES)
def test_no_product_vocabulary_and_no_call_to_action(name):
    text, raw = _read(name)
    meta = " ".join(re.findall(r'<meta (?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)" content="(.*?)">', raw))
    low = f"{text} {meta}".lower()
    for word in FORBIDDEN:
        assert word not in low, word
    assert "mailto:" not in raw and "book a" not in raw.lower()


def test_the_homepage_lists_the_eu_note():
    assert 'href="/notes/eu-ai-act-high-risk-deadline-moved.html"' in (ROOT / "index.html").read_text(encoding="utf-8")
