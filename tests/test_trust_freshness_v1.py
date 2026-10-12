"""The trust page's freshness line must stay true after the day it was
rendered. A static page cannot count days, so it states the date the
bundle was generated and the date after which it is stale, and never a
verdict or an age that was only right at render time. A test then fails
once the published bundle is past that date, so it gets regenerated.
"""
import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "trust" / "index.html"
SAMPLE = ROOT / "tests" / "fixtures" / "trust_bundle_sample.json"

_spec = importlib.util.spec_from_file_location("render_trust_page", ROOT / "scripts" / "render_trust_page.py")
renderer = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = renderer
_spec.loader.exec_module(renderer)


def _freshness_cell(page: str) -> str:
    return re.search(r"<tr><th>Freshness</th><td[^>]*>(.*?)</td></tr>", page, flags=re.S).group(1)


def test_freshness_line_names_both_dates_and_the_limit():
    line = renderer.freshness_statement("2026-09-21T12:56:56.360053+00:00")
    assert "2026-09-21" in line
    assert "2026-12-20" in line  # 90 days later
    assert "90 days" in line


def test_freshness_line_carries_nothing_that_goes_out_of_date():
    line = renderer.freshness_statement("2026-09-21T12:56:56.360053+00:00")
    assert "FRESH" not in line and "ago" not in line and "day(s)" not in line


def test_stale_check_uses_the_real_age():
    generated = "2026-09-21T12:56:56+00:00"
    at = lambda day: datetime.datetime.fromisoformat(day + "T00:00:00+00:00")  # noqa: E731
    assert renderer.is_stale(generated, now=at("2026-12-19")) is False
    assert renderer.is_stale(generated, now=at("2026-12-21")) is True


def test_rendering_a_stale_bundle_says_stale():
    bundle = json.loads(SAMPLE.read_text())
    bundle["payload"]["generated_at"] = "2020-01-01T00:00:00+00:00"
    assert "STALE" in _freshness_cell(renderer.render(bundle))


def test_published_page_has_no_baked_age_and_is_within_its_limit():
    page = PUBLISHED.read_text(encoding="utf-8")
    cell = _freshness_cell(page)
    assert "ago" not in cell and "day(s)" not in cell
    generated = re.search(r"<tr><th>Generated at</th><td>(.*?)</td></tr>", page).group(1)
    assert generated[:10] in cell
    assert not renderer.is_stale(generated), (
        "the published trust bundle is past its freshness limit: regenerate it and re-render the page"
    )
