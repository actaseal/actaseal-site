"""The sitemap must match the pages that actually exist, in both directions."""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sitemap  # noqa: E402


def _sitemap_urls():
    xml = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    return set(re.findall(r"<loc>([^<]+)</loc>", xml))


def test_sitemap_exists():
    assert (ROOT / "sitemap.xml").exists(), "sitemap.xml is missing"


def test_every_page_is_listed():
    expected = {gen_sitemap.url_for(rel) for rel in gen_sitemap.pages()}
    missing = expected - _sitemap_urls()
    assert not missing, f"pages absent from sitemap.xml: {sorted(missing)}"


def test_every_listed_url_has_a_file():
    expected = {gen_sitemap.url_for(rel) for rel in gen_sitemap.pages()}
    extra = _sitemap_urls() - expected
    assert not extra, f"sitemap.xml lists urls with no file: {sorted(extra)}"


def test_sitemap_is_current():
    """Regenerating must not change the committed file."""
    assert gen_sitemap.build() == (ROOT / "sitemap.xml").read_text(encoding="utf-8"), (
        "sitemap.xml is stale -- run scripts/gen_sitemap.py"
    )


def test_robots_points_at_the_sitemap():
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    assert "https://actaseal.com/sitemap.xml" in robots


def test_security_txt_has_required_fields():
    txt = (ROOT / ".well-known" / "security.txt").read_text(encoding="utf-8")
    for field in ("Contact:", "Expires:", "Canonical:", "Policy:"):
        assert field in txt, f"security.txt missing {field}"


def test_every_page_has_og_tags():
    bad = []
    for rel in gen_sitemap.pages():
        html = (ROOT / rel).read_text(encoding="utf-8")
        for needed in ('property="og:title"', 'property="og:url"', 'property="og:image"'):
            if needed not in html:
                bad.append(f"{rel} missing {needed}")
    assert not bad, bad
