"""2026-10-26: the homepage follows a buyer's journey (what it is -> what it does -> the easy start ->
check it yourself -> what is changing -> the open work -> book a call), moves without a single
script (CSS only, and nothing moves for a reader who asked for reduced motion), the radar draws an
actual radar from the notes' own metadata, the notes page pins what needs action now, and the
about page answers the buyer's question before the background."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_homepage_sections_follow_the_buyer_journey():
    ids = re.findall(r'<section id="([\w-]+)"', page("index.html"))
    assert ids == ["what", "product", "pilot", "check", "why-now", "proof", "book"]


def test_the_check_section_sends_the_reader_to_a_sample_record_and_says_where_data_stays():
    check = re.search(r'<section id="check".*?</section>', page("index.html"), re.S).group(0)
    assert 'href="https://verify.actaseal.com/browser/"' in check
    assert "Your payment data does not leave your environment." in check


def test_the_easy_start_is_a_three_step_ladder():
    pilot = re.search(r'<section id="pilot".*?</section>', page("index.html"), re.S).group(0)
    assert len(re.findall(r'<li class="ladder-step">', pilot)) == 3


def test_the_homepage_moves_with_css_only_and_respects_reduced_motion():
    src, css = page("index.html"), page("css/base.css")
    assert "<script" not in src.lower()
    assert "@keyframes" in css and "prefers-reduced-motion: reduce" in css
    assert "animation-timeline: view()" in css and "@supports (animation-timeline: view())" in css


def test_the_radar_page_draws_a_radar_with_one_linked_blip_per_item():
    src = page("radar/index.html")
    svg = re.search(r'<svg class="radar-scope".*?</svg>', src, re.S).group(0)
    blips = re.findall(r'<a href="/notes/([\w-]+\.html)"[^>]*>\s*<circle class="blip status-', svg)
    assert len(blips) == len(re.findall(r"<li data-region=", src))
    for q in ("India", "EU", "US", "Global"):
        assert f">{q}</text>" in svg


def test_notes_page_pins_act_now_notes():
    pinned = re.search(r'<section class="notes-pinned">.*?</section>', page("notes/index.html"), re.S).group(0)
    assert "cert-in-ai-agents-advisory.html" in pinned


def test_about_answers_the_buyer_before_the_standards_work():
    src = page("about/index.html")
    assert src.index("What that means for a buyer") < src.index("<h2>Standards work</h2>")
