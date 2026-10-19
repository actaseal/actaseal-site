"""The CERT-In note says what it was given to say, as the outlet reported it; no product vocabulary, no call to action."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "notes" / "cert-in-ai-agents-advisory.html"
SOURCE = "https://www.medianama.com/2026/10/223-cert-in-ai-agents-unauthorised-access/"
TRACKER = Path.home() / "a/active_code/docs/internal/regulatory_dates.md"

REQUIRED = [
    "CERT-In on AI agents: could you show what the agent did?",
    "On 15 October 2026 CERT-In issued an advisory it rated critical. As MediaNama reported it, AI agents, some of "
    "them run by model providers during testing, reached live systems of Indian organisations and read business "
    "records and personal data. The organisations did not notice.",
    "Among its recommendations: give AI agents separate, short-lived identities, define their task boundaries and "
    "stop a run that crosses them, and keep tamper-resistant activity logs for agents for at least 180 days.",
    "For any bank, NBFC or fintech running agents, the question is now concrete: if an agent touched something it "
    "should not have, could you show exactly what it did, and could anyone trust that record?",
    "This is a reading of public reporting, not legal advice.",
    "Source: MediaNama, October 2026.",
]
# "tamper-resistant" is the advisory's own recommendation, quoted; the product's own term is not used
FORBIDDEN = ("receipt", "signed", "verif", "ledger", "offline", "policy", "attest", "evidence pack", "tamper-evident", "gateway")


def _read():
    raw = NOTE.read_text(encoding="utf-8")
    body = re.search(r"<article>.*?</article>", raw, re.S).group(0)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip(), raw


def test_the_note_says_exactly_what_it_was_given_to_say():
    text, _ = _read()
    for piece in REQUIRED:
        assert piece in text, piece


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


def test_the_dates_tracker_has_the_row():
    if not TRACKER.exists():
        return
    row = next(l for l in TRACKER.read_text(encoding="utf-8").splitlines() if l.startswith("| CERT-In advisory on AI agents"))
    assert "15 October 2026" in row and "critical" in row and "secondary" in row and "180 days" in row and SOURCE in row
