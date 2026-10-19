"""The FSB note says what it was given to say, uses no product vocabulary and carries no call to action."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "notes" / "fsb-ai-sound-practices-for-agents.html"
SOURCE = "https://www.fsb.org/2026/10/sound-practices-for-responsible-adoption-of-artificial-intelligence-ai-final-report/"
TRACKER = Path.home() / "a/active_code/docs/internal/regulatory_dates.md"

REQUIRED = [
    "FSB's AI sound practices, read for AI agents that move money",
    "On 15 October 2026 the Financial Stability Board published its final report, Sound Practices for "
    "Responsible Adoption of Artificial Intelligence: twelve non-binding practices for financial institutions.",
    "The report is technology-neutral and mentions agentic AI only in its introduction. Read with AI agents "
    "in mind, four practices meet at one point:",
    "Practice 3 asks institutions to document their use of AI.",
    "Practice 9 asks them to evaluate AI performance in proportion to materiality and risk, including ongoing monitoring.",
    "Practice 10 asks for human oversight relevant to the materiality, risk, autonomy, complexity and "
    "explainability of each use case.",
    "Practice 12 asks them to manage risks from third-party AI, including transparency.",
    "Once an agent can move money, all four come down to one question a bank will be asked by its board, "
    "its auditor or its regulator: when the agent acted, can you prove what happened to someone who has no "
    "reason to believe you?",
    "Most teams would answer with their own logs. A log kept by the party being questioned is testimony, not proof.",
    "This is a reading of the report, not legal advice, and it does not make any system compliant with anything.",
    "Source: Financial Stability Board, Sound Practices for Responsible Adoption of Artificial Intelligence (AI): "
    "Final report, 15 October 2026.",
]
FORBIDDEN = ("receipt", "signed", "verif", "ledger", "offline", "policy", "attest", "evidence pack")


def _text():
    raw = NOTE.read_text(encoding="utf-8")
    body = re.search(r"<article>.*?</article>", raw, re.S).group(0)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip(), raw


def test_the_note_says_exactly_what_it_was_given_to_say():
    text, _ = _text()
    for piece in REQUIRED:
        assert piece in text, piece


def test_it_is_a_note_like_the_others_with_a_review_line_and_a_link_to_the_source():
    text, raw = _text()
    assert re.search(r'<time datetime="2026-10-19">19 October 2026</time> &middot; Xavier Goshi &middot; Last reviewed: '
                     r'<time class="reviewed" datetime="2026-10-19">19 October 2026</time>', raw)
    assert f'<a href="{SOURCE}">' in raw
    assert raw.count("<li>") == 4


def test_no_product_vocabulary_and_no_call_to_action():
    text, raw = _text()
    meta = " ".join(re.findall(r'<meta (?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)" content="(.*?)">', raw))
    title = re.search(r"<title>(.*?)</title>", raw).group(1).replace("&middot; ActaSeal", "")
    low = f"{text} {meta} {title}".lower()
    for word in FORBIDDEN:
        assert word not in low, word
    assert "mailto:" not in raw and "book a demo" not in raw.lower() and "pip install" not in raw


def test_the_dates_tracker_has_the_row():
    if not TRACKER.exists():
        return
    row = next(l for l in TRACKER.read_text(encoding="utf-8").splitlines() if l.startswith("| FSB Sound Practices"))
    assert "15 October 2026" in row and "VERIFIED" in row and "primary" in row and SOURCE in row
