"""The site carries the final logo: lockup in the header (light and dark), favicon, touch icon and social
image from the kit, on every page, and nothing of the old text wordmark is left."""
import hashlib
import re
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import os
KIT = Path(os.environ.get("ACTASEAL_BRAND_KIT", str(Path.home() / "a/active_code/brand/final")))
SKIP = {"tests", "scripts", ".git", ".hypothesis"}
ICON_BLOCK = (
    '<link rel="icon" href="/favicon.ico" sizes="any">',
    '<link rel="icon" href="/brand/actaseal-favicon.svg" type="image/svg+xml">',
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
)


def pages():
    return [p for p in sorted(ROOT.rglob("*.html")) if not SKIP & set(p.relative_to(ROOT).parts)]


def test_every_page_declares_the_three_icons_once():
    for page in pages():
        text = page.read_text(encoding="utf-8")
        for line in ICON_BLOCK:
            assert text.count(line) == 1, f"{page.relative_to(ROOT)}: {line}"
        assert 'href="favicon.ico"' not in text and 'href="../favicon.ico"' not in text


def test_every_header_shows_the_lockup_in_both_colour_schemes_and_no_text_wordmark():
    headers = 0
    for page in pages():
        text = page.read_text(encoding="utf-8")
        if '<header class="site-head">' not in text:
            continue
        headers += 1
        head = re.search(r'<header class="site-head">.*?</header>', text, re.S).group(0)
        assert '<source media="(prefers-color-scheme: dark)" srcset="/brand/actaseal-lockup-paper.svg">' in head, page
        assert re.search(r'<img src="/brand/actaseal-lockup-oxblood\.svg" alt="ActaSeal" width="\d+" height="\d+">', head), page
        assert '<span class="dot">' not in text, page
    assert headers >= 9


def test_the_files_the_pages_name_exist_and_match_the_kit():
    for name in ("brand/actaseal-lockup-oxblood.svg", "brand/actaseal-lockup-paper.svg",
                 "brand/actaseal-seal-small-oxblood.svg", "brand/actaseal-favicon.svg", "favicon.ico", "apple-touch-icon.png", "og-image.png"):
        assert (ROOT / name).is_file(), name
    if not KIT.exists():
        pytest.skip("the product repository's brand/final is not on this machine")
    for name in ("actaseal-lockup-oxblood.svg", "actaseal-lockup-paper.svg", "actaseal-seal-small-oxblood.svg"):
        assert (ROOT / "brand" / name).read_bytes() == (KIT / name).read_bytes(), name
    for name in ("favicon.ico", "apple-touch-icon.png"):
        assert (ROOT / name).read_bytes() == (KIT / name).read_bytes(), name
    # H14: the tab icon draws the hash in paper colour; the small seal's hash is a hole that shows the tab colour
    assert (ROOT / "brand" / "actaseal-favicon.svg").read_bytes() == (KIT / "actaseal-favicon-oxblood.svg").read_bytes()


def test_the_social_image_is_1200_by_630_and_every_page_points_at_it():
    data = (ROOT / "og-image.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (1200, 630)
    for page in pages():
        text = page.read_text(encoding="utf-8")
        assert '<meta property="og:image" content="https://actaseal.com/og-image.png">' in text, page


def test_the_old_logo_files_are_gone():
    old = {"78531bfa0dfab80d"}   # the old document-and-seal og-image
    assert hashlib.sha256((ROOT / "og-image.png").read_bytes()).hexdigest()[:16] not in old
    assert not list(ROOT.glob("*.svg"))
