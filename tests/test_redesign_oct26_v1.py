"""2026-10-26 pass: outcomes under each homepage benefit, a named use for each kind of buyer, a
mobile-only bar to the refund audit (CSS, no script on the homepage), an example report and the
audit -> pilot -> production ladder on /refunds/, what success means on /pilot/, and a radar that
reads as a radar: deadline cards, coloured status, an "act now" box, what each item means for a
team whose agent moves money, when it was last updated, how items are chosen, and one way forward.
Nothing invented: no customer names, no logos, no prices."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))


def test_each_homepage_benefit_ends_in_an_outcome():
    outcomes = re.findall(r'<p class="step-outcome">(.*?)</p>', page("index.html"), re.S)
    assert len(outcomes) == 3 and all(o.strip().startswith("So ") for o in outcomes)


def test_the_homepage_names_a_use_for_each_buyer():
    t = text(page("index.html"))
    for use in ("refunds and credits", "agent-initiated payouts", "testing AI agents that move money"):
        assert use in t, use


def test_a_mobile_bar_points_at_the_refund_audit_without_script():
    src = page("index.html")
    assert re.search(r'<div class="sticky-cta"><a href="/refunds/">Start a refund audit</a></div>', src)
    assert "<script" not in src.lower()
    css = page("css/base.css")
    assert ".sticky-cta" in css and "position: sticky" in css


def test_the_refund_page_shows_an_example_report_marked_as_made_up():
    src = page("refunds/index.html")
    report = re.search(r'<table class="example-report">.*?</table>', src, re.S).group(0)
    assert "Example with made-up figures" in text(src) and report.count("<tr>") >= 4


def test_the_refund_page_shows_what_comes_after():
    t = text(page("refunds/index.html"))
    assert "Refund audit" in t and "Paid pilot" in t and "In production" in t


def test_the_pilot_page_says_what_success_looks_like():
    assert "What success looks like" in text(page("pilot/index.html"))


def test_no_invented_proof_or_price_anywhere_new():
    for rel in ("index.html", "refunds/index.html", "pilot/index.html", "radar/index.html"):
        low = text(page(rel)).lower()
        for word in ("trusted by", "used by", "customers include", "case study", "$", "₹", "per month", "per year"):
            assert word not in low, (rel, word)


# --- radar ---------------------------------------------------------------

def test_radar_deadline_cards_status_colours_and_act_now_box():
    src = page("radar/index.html")
    cards = re.findall(r'<li class="deadline-card" data-date="([\d-]+)">', src)
    assert cards == sorted(cards) and len(cards) >= 2
    for status in ("in-force", "coming", "draft", "guidance", "signal"):
        assert f".status-{status}" in page("css/base.css")
    box = re.search(r'<section class="act-now-box">.*?</section>', src, re.S).group(0)
    assert "cert-in-ai-agents-advisory.html" in box


def test_each_radar_entry_says_what_it_means_for_a_team_whose_agent_moves_money():
    src = page("radar/index.html")
    items = re.findall(r'<li data-region=.*?</li>', src, re.S)
    assert items and all('<p class="radar-means">If your agent moves money: ' in i for i in items)


def test_radar_says_when_it_was_updated_how_items_are_chosen_and_one_way_forward():
    t = text(page("radar/index.html"))
    assert re.search(r"Last updated: \d{4}-\d{2}-\d{2}", t)
    assert "Only public sources that can be cited" in t
    assert "Start with a refund audit" in t and "Book a 20-min call" in t
