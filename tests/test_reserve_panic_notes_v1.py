"""The three Shopify reserve/payout-hold answer pages: each answers in its
first lines, cites Shopify's own help pages, links the appeal builder, and
its FAQ data says exactly what the page shows."""
import html
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "shopify-payments-reserve-120-days.html": ("120 days", "help.shopify.com/en/manual/payments/shopify-payments/reserves"),
    "shopify-payouts-on-hold-while-we-review-your-account.html": (
        "on hold while we review your account", "help.shopify.com/en/manual/payments/shopify-payments/account-holds"),
    "shopify-reserve-expired-funds-not-received.html": ("expired", "help.shopify.com/en/manual/payments/shopify-payments/reserves"),
}


def _src(name):
    return (ROOT / "notes" / name).read_text(encoding="utf-8")


def _visible(src):
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", src, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))


def _faq(src):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', src, re.S)
    assert len(blocks) == 1
    data = json.loads(blocks[0])
    assert data["@type"] == "FAQPage"
    return data["mainEntity"]


@pytest.mark.parametrize("name", PAGES)
def test_the_page_matches_the_search_phrase_and_answers_first(name):
    src = _src(name)
    phrase, _ = PAGES[name]
    h1 = html.unescape(re.search(r"<h1>(.*?)</h1>", src, re.S).group(1))
    assert phrase.lower() in h1.lower()
    # the first thing after the heading is the answer, in two sentences at most
    after = src.split("</h1>", 1)[1].lstrip()
    lede = re.match(r'<p class="lede">(.*?)</p>', after, re.S)
    assert lede, "answer must come straight after the heading"
    text = html.unescape(lede.group(1))
    assert text.startswith("Short answer:")
    assert len(re.findall(r"[.!?](?:\s|$)", text)) <= 2


@pytest.mark.parametrize("name", PAGES)
def test_the_page_cites_shopify_and_links_the_appeal_builder(name):
    src = _src(name)
    _, help_url = PAGES[name]
    assert f'href="https://{help_url}"' in src
    assert 'href="/reserve-rescue/"' in src
    # no page claims to speak for Shopify
    assert "does not speak for Shopify" in _visible(src)


@pytest.mark.parametrize("name", PAGES)
def test_faq_data_is_exactly_what_the_page_shows_question_by_question(name):
    src = _src(name)
    pairs = [(html.unescape(q), html.unescape(a))
             for q, a in re.findall(r"<h2>(.*?)</h2>\s*<p>(.*?)</p>", src, re.S)]
    faq = [(i["name"], i["acceptedAnswer"]["text"]) for i in _faq(src)]
    assert len(faq) >= 4
    assert pairs == faq
    assert len(re.findall(r"<h2>", src)) == len(faq)


@pytest.mark.parametrize("name", PAGES)
def test_structured_data_cannot_break_out_of_its_script(name):
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', _src(name), re.S).group(1)
    assert "</" not in block and "<!--" not in block


@pytest.mark.parametrize("name", PAGES)
def test_every_shopify_source_is_allowlisted_and_timing_claims_cite_the_payout_page(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_links", ROOT / "scripts" / "check_links.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = _src(name)
    for url in re.findall(r'href="(https://help\.shopify\.com[^"]*)"', src):
        assert any(url.startswith(p) for p in mod.ALLOWED_EXTERNAL_PREFIXES), url
    if "up to 5 business days" in _visible(src):
        assert "shopify-balance/payouts/payout-accounts" in src


OVERCLAIMS = ("guarantee", "we will get", "shopify will release", "always", "common causes",
              "only by replying", "it will be corrected", "we can get your", "we recover")


@pytest.mark.parametrize("name", PAGES)
def test_no_outcome_promises_or_overclaims(name):
    shown = _visible(_src(name)).lower()
    for word in OVERCLAIMS:
        assert word not in shown, word
    assert "not legal or financial advice" in shown


@pytest.mark.parametrize("name", PAGES)
def test_the_page_runs_no_script_and_loads_nothing_external(name):
    src = _src(name)
    without_ld = re.sub(r'<script type="application/ld\+json">.*?</script>', "", src, flags=re.S)
    assert "<script" not in without_ld.lower()
    assert "<form" not in src.lower()
    low = src.lower()
    for bad in ("<base", "http-equiv", "url(", "<style", " style="):
        assert bad not in low, bad
    for tag in re.findall(r"<(?!a\b)[a-z]+\b[^>]*>", src):
        for url in re.findall(r'\b(?:src|href|srcset|data|poster)="([^"]+)"', tag):
            if tag.startswith("<link") and 'rel="canonical"' in tag:
                continue
            assert not url.startswith(("//", "http")), url
    for tag in re.findall(r"<a\b[^>]*>", src):
        if 'target="_blank"' in tag:
            assert "noopener" in tag
    canon = re.search(r'rel="canonical" href="([^"]+)"', src).group(1)
    assert f'<meta property="og:url" content="{canon}">' in src


@pytest.mark.parametrize("name", PAGES)
def test_the_page_is_listed_for_answer_engines_sitemap_and_notes(name):
    url = "https://actaseal.com/notes/" + name
    assert url in (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert f"<loc>{url}</loc>" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    assert name in (ROOT / "notes" / "index.html").read_text(encoding="utf-8")
    assert f'rel="canonical" href="{url}"' in _src(name)


def _lede_ok(src):
    after = src.split("</h1>", 1)[1].lstrip()
    m = re.match(r'<p class="lede">(.*?)</p>', after, re.S)
    return bool(m) and html.unescape(m.group(1)).startswith("Short answer:")


def test_the_answer_check_fails_on_a_real_page_with_the_answer_moved():
    src = _src(next(iter(PAGES)))
    assert _lede_ok(src)
    moved = src.replace("</h1>\n", "</h1>\n<p>Some intro first.</p>\n", 1)
    assert not _lede_ok(moved)
    faq_broken = re.sub(r"(<h2>[^<]*</h2>\s*<p>)", r"\1x", src, count=1)
    pairs = re.findall(r"<h2>(.*?)</h2>\s*<p>(.*?)</p>", faq_broken, re.S)
    assert [html.unescape(a) for _, a in pairs] != [i["acceptedAnswer"]["text"] for i in _faq(src)]
