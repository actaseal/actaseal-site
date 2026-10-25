#!/usr/bin/env python3
"""Build notes/index.html from the note files that exist.

A note is any notes/*.html except index.html. Each must carry a <time datetime="...">,
an author line and a "Last reviewed" date; tests/test_notes_v1.py enforces that and enforces that the index
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
        reviewed = re.search(r'<time class="reviewed" datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})"', s)
        level = re.search(r'<meta name="actaseal:criticality" content="([0-3])">', s)
        source = re.search(r'<meta name="actaseal:source-date" content="([0-9]{4}-[0-9]{2}-[0-9]{2})">', s)
        if not (date and title):
            raise SystemExit(f"{p.name}: needs a <time datetime> and an <h1>")
        if not (level and source):
            raise SystemExit(f"{p.name}: needs actaseal:criticality (0-3) and actaseal:source-date metas")
        out.append({
            "file": p.name,
            "date": date.group(1),
            "criticality": int(level.group(1)),
            "source_date": source.group(1),
            "reviewed": reviewed.group(1) if reviewed else date.group(1),
            "title": re.sub(r"\s+", " ", title.group(1)).strip(),
            "summary": re.sub(r"\s+", " ", desc.group(1)).strip() if desc else "",
        })
    return sorted(out, key=lambda n: (n["source_date"], n["criticality"], n["date"], n["file"]), reverse=True)


LEVELS = {3: "Act now", 2: "Prepare", 1: "Watch"}

FILTER = """<div class="note-filter" role="group" aria-label="Show notes by how soon they need action" hidden>
  <button type="button" data-level="all" aria-pressed="true">All</button>
  <button type="button" data-level="3" aria-pressed="false">Act now</button>
  <button type="button" data-level="2" aria-pressed="false">Prepare</button>
  <button type="button" data-level="1" aria-pressed="false">Watch</button>
</div>
<p class="note-filter-help" hidden>All: newest source first. Act now: in force or rated critical. Prepare: rules on the way. Watch: guidance worth knowing.</p>"""

SCRIPT = """<script>
(function () {
  var bar = document.querySelector(".note-filter");
  var help = document.querySelector(".note-filter-help");
  var items = document.querySelectorAll(".note-list li");
  bar.hidden = false; help.hidden = false;
  bar.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    bar.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
    items.forEach(function (li) {
      li.hidden = b.dataset.level !== "all" && li.dataset.criticality !== b.dataset.level;
    });
  });
})();
</script>"""


def _badge(level: int) -> str:
    if level not in LEVELS:
        return ""
    return f' <span class="crit crit-{level}">{LEVELS[level]}</span>'



def build() -> str:
    items = "\n".join(
        f'  <li data-criticality="{n["criticality"]}" data-source-date="{n["source_date"]}">\n'
        f'    <time datetime="{n["date"]}">{n["date"]}</time>{_badge(n["criticality"])}\n'
        f'    <a href="{n["file"]}">{html.escape(n["title"])}</a>\n'
        f'    <p>{html.escape(n["summary"])}</p>\n'
        f'    <p class="note-meta">Source published: <time class="source" datetime="{n["source_date"]}">{n["source_date"]}</time> &middot; Last reviewed: <time class="reviewed" datetime="{n["reviewed"]}">{n["reviewed"]}</time></p>\n'
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
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/brand/actaseal-favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
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
{FILTER}
<ul class="note-list">
{items}
</ul>
{SCRIPT}
<p>CBOM semantic checker: <a href="https://github.com/actaseal/cbom-check">github.com/actaseal/cbom-check</a>.</p>
<p><a href="/">Back to actaseal.com</a></p>
</main>
</body>
</html>
"""


if __name__ == "__main__":
    (NOTES / "index.html").write_text(build(), encoding="utf-8")
    print(f"notes/index.html: {len(notes())} note(s)")
