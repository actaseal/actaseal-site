"""The Terms and the DPA point at the order form for the contracting entity and show no unfinished placeholder;
the engagement letter is not a published page."""
import html
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("page", ["legal/terms.html", "legal/dpa.html"])
def test_entity_is_named_in_the_order_form_and_no_placeholder_shows(page):
    text = html.unescape(re.sub(r"<[^>]+>", " ", (ROOT / page).read_text(encoding="utf-8")))
    assert "The contracting entity is named in your order form." in text
    assert "DECIDE" not in text


def test_engagement_letter_is_not_published():
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or "tests" in path.parts:
            continue
        assert "engagement-letter" not in path.name.lower() and "engagement_letter" not in path.name.lower(), path
    for page in ROOT.rglob("*.html"):
        if "tests" in page.parts:
            continue
        assert "engagement letter" not in page.read_text(encoding="utf-8").lower(), page
