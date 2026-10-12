"""The homepage leads with one buyer and one outcome.

The headline is fixed wording. The first screen speaks to a company that
sells AI agents to enterprises; audit archives and legal hold are named
further down, as a secondary use, not as a list of target groups.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"
HEADLINE = "Proof of what your AI agents did — that your customer can verify without trusting us."


def _raw() -> str:
    return PAGE.read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _main_text() -> str:
    return _text(re.search(r"<main\b.*?</main>", _raw(), flags=re.S).group(0))


def test_headline_is_the_agreed_wording():
    headings = re.findall(r"<h1\b[^>]*>(.*?)</h1>", _raw(), flags=re.S)
    assert [_text(h) for h in headings] == [HEADLINE]


def test_page_title_and_share_text_match_the_headline():
    raw = html.unescape(_raw())
    assert "Proof of what your AI agents did" in re.search(r"<title>(.*?)</title>", raw, flags=re.S).group(1)
    for prop in ('property="og:description"', 'name="twitter:description"', 'name="description"'):
        tag = re.search(r"<meta[^>]+" + re.escape(prop) + r"[^>]*>", raw).group(0)
        assert "customer" in tag and "audit workflows" not in tag, tag


def test_first_paragraph_speaks_to_companies_selling_agents_to_enterprises():
    lede = _text(re.search(r'<p class="lede">(.*?)</p>', _raw(), flags=re.S).group(1))
    assert "enterprise" in lede.lower()
    assert "agent" in lede.lower()
    assert "receipt" in lede.lower()


def test_no_list_of_target_groups():
    raw = _raw()
    text = _main_text()
    assert "Three groups" not in text
    assert "who-row" not in raw
    for label in ("Audit firms", "Legal hold and med-mal", "Agent-commerce disputes"):
        assert not re.search(r"<(dt|h3|li)[^>]*>\s*" + re.escape(label), raw), f"{label!r} is still a listed group"


def test_audit_and_legal_hold_are_named_but_come_second():
    text = _main_text()
    assert "AS 1215" in text and "legal hold" in text.lower()
    assert text.index(HEADLINE) < text.index("AS 1215")
    lede = _text(re.search(r'<p class="lede">(.*?)</p>', _raw(), flags=re.S).group(1))
    assert "AS 1215" not in lede and "legal hold" not in lede.lower()
    for heading in re.findall(r"<h[12]\b[^>]*>(.*?)</h[12]>", _raw(), flags=re.S):
        assert "AS 1215" not in _text(heading)


def test_no_strategy_or_roadmap_language():
    low = _main_text().lower()
    for phrase in ("roadmap", "wedge", "segment", "go-to-market", "coming soon", "planned"):
        assert phrase not in low, f"homepage says {phrase!r}"


# --- open core: one outcome sentence, no feature split ---------------------

def _open_core() -> str:
    return re.search(r'<section id="open-core">.*?</section>', _raw(), flags=re.S).group(0)


def test_open_core_is_one_sentence_about_what_is_open_and_what_is_licensed():
    text = _text(_open_core())
    assert "The verifier and the evidence pack format are free and open under the Apache License 2.0" in text
    assert "The product is licensed" in text
    assert "<li" not in _open_core() and "<ul" not in _open_core()


def test_open_core_has_no_feature_split_or_watermark_talk():
    low = _text(_open_core()).lower()
    for phrase in ("free forever", "licensed (", "watermark", "unlicensed", "evaluation copy", "questionnaire",
                   "route coverage", "per-control"):
        assert phrase not in low, f"open-core section says {phrase!r}"
    assert "watermark" not in _main_text().lower()
