"""/radar/: every regulatory note in one place, filterable by region and status, with the dates
still ahead on a timeline. Built from the notes' own metadata by scripts/gen_notes.py, so it
cannot drift from them; a note without region and status is not on the radar."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gen_notes  # noqa: E402

RADAR = ROOT / "radar" / "index.html"
EXPECTED = {
    "cert-in-ai-agents-advisory.html": ("India", "In force", None),
    "npci-agents-on-upi.html": ("India", "Signal", None),
    "colorado-sb-26-189.html": ("US", "Coming", "2027-01-01"),
    "eu-ai-act-high-risk-deadline-moved.html": ("EU", "Coming", "2027-12-02"),
    "fsb-ai-sound-practices-for-agents.html": ("Global", "Guidance", None),
    "emvco-agentic-payments-framework.html": ("Global", "Draft", None),
    "us-banks-block-ai-agents.html": ("US", "Signal", None),
    "us-bank-regulators-ask-about-ai-agents.html": ("US", "Signal", None),
}


def test_radar_notes_carry_region_status_and_deadline():
    on_radar = {n["file"]: (n["region"], n["status"], n["deadline"]) for n in gen_notes.notes() if n["region"]}
    assert on_radar == EXPECTED


def test_the_radar_page_is_current_and_lists_each_radar_note():
    assert gen_notes.build_radar() == RADAR.read_text(encoding="utf-8"), "radar is stale -- run scripts/gen_notes.py"
    page = RADAR.read_text(encoding="utf-8")
    for name, (region, status, _) in EXPECTED.items():
        assert re.search(rf'<li data-region="{region}" data-status="{status}"[^>]*>.*?href="/notes/{name}"', page, re.S), name


def test_the_timeline_shows_only_dates_still_ahead_newest_last():
    page = RADAR.read_text(encoding="utf-8")
    timeline = re.search(r'<ol class="radar-timeline">(.*?)</ol>', page, re.S).group(1)
    dates = re.findall(r'<time datetime="(\d{4}-\d{2}-\d{2})"', timeline)
    assert dates == sorted(dates) and "2027-01-01" in dates and "2027-12-02" in dates


def test_filters_for_region_and_status():
    page = RADAR.read_text(encoding="utf-8")
    assert re.findall(r'data-filter="region" data-value="(\w+)"', page) == ["all", "India", "EU", "US", "Global"]
    assert re.findall(r'data-filter="status" data-value="([\w ]+)"', page) == [
        "all", "In force", "Coming", "Draft", "Guidance", "Signal"]


def test_reachable_from_notes_and_homepage_and_sitemap():
    assert 'href="/radar/"' in (ROOT / "notes" / "index.html").read_text(encoding="utf-8")
    assert 'href="/radar/"' in (ROOT / "index.html").read_text(encoding="utf-8")
    assert "https://actaseal.com/radar/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_no_product_vocabulary_on_the_radar():
    low = re.sub(r"<[^>]+>", " ", RADAR.read_text(encoding="utf-8")).lower()
    for word in ("receipt", "signed", "ledger", "offline", "gateway", "tamper", "attest"):
        assert word not in low, word


def test_no_title_is_escaped_twice():
    for page in (RADAR, ROOT / "notes" / "index.html"):
        assert "&amp;#x27;" not in page.read_text(encoding="utf-8") and "&amp;amp;" not in page.read_text(encoding="utf-8")
