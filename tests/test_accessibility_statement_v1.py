"""The accessibility page's numbers must match the audit output it publishes."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "accessibility" / "index.html"
DATA = ROOT / "accessibility" / "findings.json"


def _counts():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    return (
        len(d["axe_violations_by_tab"]),
        sum(len(v) for v in d["axe_violations_by_tab"].values()),
        sum(len(v) for v in d["missing_focus_indicator_by_tab"].values()),
        sum(len(v) for v in d["undersized_targets_by_tab"].values()),
    )


def test_both_files_exist():
    assert PAGE.exists() and DATA.exists()


def test_page_numbers_match_the_findings_file():
    surfaces, axe, focus, targets = _counts()
    html = PAGE.read_text(encoding="utf-8")
    assert f"<strong>{axe}</strong> automated violation" in html
    assert f"<strong>{focus}</strong> element" in html
    assert f"<strong>{targets}</strong> element" in html
    assert f"across all {surfaces} surfaces" in html


def test_every_open_finding_is_listed():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    html = PAGE.read_text(encoding="utf-8")
    for tab, violations in d["axe_violations_by_tab"].items():
        for v in violations:
            assert v["id"] in html, f"{tab}: axe {v['id']} not listed on the page"
    for tab, rows in d["undersized_targets_by_tab"].items():
        for r in rows:
            assert str(r["width"]) in html, f"{tab}: undersized target not listed"


def test_scope_is_not_overstated():
    html = PAGE.read_text(encoding="utf-8")
    assert "It does not\ndescribe this marketing site" in html or \
           "does not" in html and "marketing site" in html
    assert "No assistive technology was used" in html
    assert not re.search(r"fully (compliant|accessible)", html, re.I)
    assert not re.search(r"WCAG 2\.2 AA (compliant|certified)", html, re.I)
