"""The AS 1215 and About pages describe the product and name who stands
behind it. They do not describe the size or stage of the company."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    raw = (ROOT / rel).read_text(encoding="utf-8")
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def test_as1215_has_no_company_stage_statements():
    low = _text("as1215/index.html").lower()
    for phrase in (
        "no audit firm is running this", "in production yet", "deployment record",
        "first firms to deploy", "terms that reflect that", "soc 2",
    ):
        assert phrase not in low, f"as1215 still says {phrase!r}"


def test_as1215_keeps_its_product_limits():
    # What the product does not do stays public.
    text = _text("as1215/index.html")
    assert "remains your firm's judgment" in text


def test_about_names_the_founder_and_has_no_headcount_statements():
    text = _text("about/index.html")
    assert "Xavier Goshi" in text
    low = text.lower()
    for phrase in ("one person", "committee", "single founder", "solo"):
        assert phrase not in low, f"about still says {phrase!r}"


def test_about_shows_no_unfinished_placeholder():
    assert "DECIDE" not in _text("about/index.html")


def test_about_has_no_certification_status_statement():
    low = _text("about/index.html").lower()
    assert "soc 2" not in low and "soc 2" not in low
    # the product-level point it sat beside stays
    assert "runs offline" in low and "apache license 2.0" in low
