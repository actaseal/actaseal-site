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
    "us-banks-block-ai-agents.html": {
        "level": "2", "source_date": "2026-10-22",
        "required": [
            "US banks are blocking AI agents. What would let one back in?",
            "On 22 October 2026 Axios reported, citing people familiar with the matter, that Morgan Stanley, "
            "JPMorgan Chase, Bank of America and Citi are restricting third-party AI agents from customer accounts",
            "Morgan Stanley said it had blocked third-party agents despite not having seen rogue AI agents.",
            "This is a reading of public reporting, not legal advice.",
        ],
        "links": ["https://paymentexpert.com/2026/10/23/ai-agents-blocked-by-banks/"],
    },
    "us-bank-regulators-ask-about-ai-agents.html": {
        "level": "2", "source_date": "2026-10-13",
        "required": [
            "US bank supervisors are asking about AI agents. Could you answer?",
            "On 13 October 2026 Reuters reported, citing people familiar with the matter, that supervisors at the "
            "Federal Reserve, the OCC and the FDIC have been asking banks about the AI agents they use.",
            "The agencies declined to comment. Nothing has been published",
            "This is a reading of public reporting, not legal advice.",
        ],
        "links": ["https://complexdiscovery.com/us-bank-regulators-ask-whether-lenders-can-stop-their-ai-agents/"],
    },
    "canadian-banks-block-ai-agents.html": {
        "level": "2", "source_date": "2026-10-28",
        "required": [
            "Canada's banks are blocking AI agents too. Who will let one in?",
            "On 28 October 2026 The Canadian Press reported that RBC, TD and BMO are blocking third-party "
            "personal AI agents from their online banking, CIBC does not support them opening or accessing "
            "accounts, and Scotiabank will limit them.",
            "This is a reading of public reporting, not legal advice.",
        ],
        "links": ["https://cp24.com/news/money/2026/10/28/some-canadian-banks-blocking-personal-ai-agents-amid-security-concerns"],
    },
    "rbi-ai-cyber-threats-advisory.html": {
        "level": "3", "source_date": "2026-06-10",
        "required": [
            "RBI on AI-accelerated cyber threats: could you show what your AI did?",
            "In early June 2026 the Reserve Bank of India issued advisories on AI-accelerated cyber threats",
            "a board-approved gap assessment and a time-bound action plan by the end of June",
            "This is a reading of public reporting and of a public summary, not legal advice.",
        ],
        "links": ["https://www.business-standard.com/industry/banking/rbi-asks-banks-to-assess-ai-risk-gaps-draw-action-plan-by-june-end-126060901145_1.html",
                  "https://kpmg.com/in/en/insights/2026/06/rbi-advisory-on-ai-accelerated-cyber-threats-and-related-safeguards.html"],
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
