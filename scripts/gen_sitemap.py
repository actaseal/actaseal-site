#!/usr/bin/env python3
"""Generate sitemap.xml from the HTML pages actually present in this repo.

Every published page must appear in the sitemap, and every URL in the sitemap
must correspond to a file that exists. tests/test_sitemap_v1.py asserts both.
"""
import datetime
import pathlib
import subprocess

BASE = "https://actaseal.com"
ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {"tests", "scripts", "node_modules", ".git", "trust/bundle"}


def pages():
    for p in sorted(ROOT.rglob("*.html")):
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        yield rel


def url_for(rel: str) -> str:
    if rel == "index.html":
        return BASE + "/"
    if rel.endswith("/index.html"):
        return BASE + "/" + rel[: -len("index.html")]
    return BASE + "/" + rel


def lastmod(rel: str) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", rel],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return datetime.date.today().isoformat()


def build() -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for rel in pages():
        lines.append("  <url>")
        lines.append(f"    <loc>{url_for(rel)}</loc>")
        lines.append(f"    <lastmod>{lastmod(rel)}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    (ROOT / "sitemap.xml").write_text(build(), encoding="utf-8")
    print(f"sitemap.xml: {sum(1 for _ in pages())} urls")
