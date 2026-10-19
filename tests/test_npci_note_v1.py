"""The NPCI note says what it was given to say: the quotes as MediaNama reported them, what is reported about NPCI's
protocol work and no more, no product vocabulary and no call to action."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "notes" / "npci-agents-on-upi.html"
SOURCE = "https://www.medianama.com/2026/09/223-npci-ai-agents-upi-payments/"
TRACKER = Path.home() / "a/active_code/docs/internal/regulatory_dates.md"

REQUIRED = [
    "NPCI on AI agents and UPI: who shows what was authorised?",
    "At Global Fintech Fest on 10 September 2026, NPCI's chairman said, as MediaNama reported it: "
    "\"AI may recommend, but authentication and final settlement must follow deterministic auditable rules.\" "
    "And: \"Decision making and execution must remain separate.\"",
    "NPCI is examining protocols for identifying and authorising digital agents on UPI, and Business Standard has "
    "reported it is building a Unified Agent Protocol; NPCI had not responded to either outlet.",
    "The open question is the one customers will ask first: when an agent pays and gets it wrong, who can show what "
    "the customer actually authorised, and who decided it was within that authority?",
    "Today the answer often sits with whoever ran the agent. That is a party to the dispute, not a witness.",
    "This is a reading of public reporting, not legal advice.",
    "Source: MediaNama, 10 September 2026.",
]
FORBIDDEN = ("receipt", "signed", "verif", "ledger", "offline", "policy", "attest", "evidence pack", "tamper", "gateway")


def _read():
    raw = NOTE.read_text(encoding="utf-8")
    body = re.search(r"<article>.*?</article>", raw, re.S).group(0)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip(), raw


def test_the_note_says_exactly_what_it_was_given_to_say():
    text, _ = _read()
    for piece in REQUIRED:
        assert piece in text, piece


def test_it_does_not_say_the_protocol_needs_rbi_approval():
    text, _ = _read()
    assert "rbi" not in text.lower() and "approval" not in text.lower()


def test_it_is_a_note_like_the_others_with_a_review_line_and_the_source_link():
    _, raw = _read()
    assert re.search(r'<time datetime="2026-10-19">19 October 2026</time> &middot; Xavier Goshi &middot; Last reviewed: '
                     r'<time class="reviewed" datetime="2026-10-19">19 October 2026</time>', raw)
    assert f'<a href="{SOURCE}">' in raw


def test_no_product_vocabulary_and_no_call_to_action():
    text, raw = _read()
    meta = " ".join(re.findall(r'<meta (?:name|property)="(?:description|og:title|og:description|twitter:title|twitter:description)" content="(.*?)">', raw))
    title = re.search(r"<title>(.*?)</title>", raw).group(1).replace("&middot; ActaSeal", "")
    low = f"{text} {meta} {title}".lower()
    for word in FORBIDDEN:
        assert word not in low, word
    assert "mailto:" not in raw and "book a" not in raw.lower() and "pip install" not in raw


def test_the_dates_tracker_has_the_quote_row_and_marks_the_rbi_point_unverified():
    if not TRACKER.exists():
        return
    row = next(l for l in TRACKER.read_text(encoding="utf-8").splitlines() if l.startswith("| NPCI on AI agents"))
    assert "VERIFIED, secondary" in row and "RBI-approval" in row and "UNVERIFIED" in row and SOURCE in row
