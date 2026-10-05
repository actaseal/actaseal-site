#!/usr/bin/env python3
"""Build notes/index.html from the note files that exist.

A note is any notes/*.html except index.html. Each must carry a <time datetime="...">
and an author line; tests/test_notes_v1.py enforces that and enforces that the index
lists exactly the notes present, in both directions.
"""
import html
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"


def notes():
    out = []
    for p in sorted(NOTES.glob("*.html")):
        if p.name == "index.html":
            continue
        s = p.read_text(encoding="utf-8")
        date = re.search(r'<time datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})"', s)
        title = re.search(r"<h1>(.*?)</h1>", s, re.S)
        desc = re.search(r'<meta name="description" content="(.*?)">', s, re.S)
        if not (date and title):
            raise SystemExit(f"{p.name}: needs a <time datetime> and an <h1>")
        out.append({
            "file": p.name,
            "date": date.group(1),
            "title": re.sub(r"\s+", " ", title.group(1)).strip(),
            "summary": re.sub(r"\s+", " ", desc.group(1)).strip() if desc else "",
        })
    return sorted(out, key=lambda n: n["date"], reverse=True)


def build() -> str:
    items = "\n".join(
        f'  <li>\n'
        f'    <time datetime="{n["date"]}">{n["date"]}</time>\n'
        f'    <a href="{n["file"]}">{html.escape(n["title"])}</a>\n'
        f'    <p>{html.escape(n["summary"])}</p>\n'
        f'  </li>'
        for n in notes()
    )
    desc = ("Working notes on evidence, verification and the standards ActaSeal is built "
            "against. Written when there is something to record, not on a schedule.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notes &middot; ActaSeal</title>
<link rel="stylesheet" href="../css/base.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ActaSeal">
<meta property="og:title" content="ActaSeal notes">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="https://actaseal.com/notes/">
<meta property="og:image" content="https://actaseal.com/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="ActaSeal notes">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="https://actaseal.com/og-image.png">
<meta name="description" content="{desc}">
</head>
<body>
<main class="wrap">
<h1>Notes</h1>
<p class="lede">{desc}</p>
<ul class="note-list">
{items}
</ul>
<p>CBOM semantic checker: <a href="https://github.com/actaseal/cbom-check">github.com/actaseal/cbom-check</a>.</p>
<p><a href="/">Back to actaseal.com</a></p>
</main>
</body>
</html>
"""


if __name__ == "__main__":
    (NOTES / "index.html").write_text(build(), encoding="utf-8")
    print(f"notes/index.html: {len(notes())} note(s)")
