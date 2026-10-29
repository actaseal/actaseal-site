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
        region = re.search(r'<meta name="actaseal:region" content="(India|EU|US|Canada|Global)">', s)
        status = re.search(r'<meta name="actaseal:status" content="(In force|Coming|Draft|Guidance|Signal)">', s)
        deadline = re.search(r'<meta name="actaseal:deadline" content="([0-9]{4}-[0-9]{2}-[0-9]{2})">', s)
        means = re.search(r'<meta name="actaseal:means" content="(.*?)">', s)
        if region and not means:
            raise SystemExit(f"{p.name}: a radar note needs actaseal:means")
        if bool(region) != bool(status):
            raise SystemExit(f"{p.name}: a radar note needs both actaseal:region and actaseal:status")
        if not (date and title):
            raise SystemExit(f"{p.name}: needs a <time datetime> and an <h1>")
        if not (level and source):
            raise SystemExit(f"{p.name}: needs actaseal:criticality (0-3) and actaseal:source-date metas")
        out.append({
            "file": p.name,
            "date": date.group(1),
            "criticality": int(level.group(1)),
            "source_date": source.group(1),
            "region": region.group(1) if region else None,
            "status": status.group(1) if status else None,
            "deadline": deadline.group(1) if deadline else None,
            "means": html.unescape(means.group(1)) if means else None,
            "reviewed": reviewed.group(1) if reviewed else date.group(1),
            "title": html.unescape(re.sub(r"\s+", " ", title.group(1)).strip()),
            "summary": html.unescape(re.sub(r"\s+", " ", desc.group(1)).strip()) if desc else "",
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



def _pinned() -> str:
    urgent = [n for n in notes() if n["criticality"] == 3]
    if not urgent:
        return ""
    rows = "\n".join(
        f'  <p><span class="crit crit-3">Act now</span> <a href="{n["file"]}">{html.escape(n["title"])}</a></p>'
        for n in urgent
    )
    return f'<section class="notes-pinned">\n  <h2>Needs attention now</h2>\n{rows}\n</section>'


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
<p>Regulators, supervisors and payment networks on AI agents, by region and status: <a href="/radar/">the radar</a>.</p>
{_pinned()}
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


REGIONS = ("India", "EU", "US", "Canada", "Global")
STATUSES = ("In force", "Coming", "Draft", "Guidance", "Signal")
STATUS_HELP = ("In force: issued and applying now. Coming: law with a date ahead. Draft: open for comment. "
               "Guidance: published, not binding. Signal: statements, supervisory questions, market moves.")

RADAR_SCRIPT = """<script>
(function () {
  var sel = {region: "all", status: "all"};
  var items = document.querySelectorAll(".radar-list li");
  document.querySelectorAll(".radar-filter").forEach(function (bar) {
    bar.hidden = false;
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      bar.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      sel[b.dataset.filter] = b.dataset.value;
      var shown = 0;
      items.forEach(function (li) {
        var ok = (sel.region === "all" || li.dataset.region === sel.region) &&
                 (sel.status === "all" || li.dataset.status === sel.status);
        li.hidden = !ok; if (ok) shown++;
      });
      document.querySelector(".radar-empty").hidden = shown > 0;
    });
  });
  var now = Date.now();
  document.querySelectorAll(".deadline-card").forEach(function (card) {
    var days = Math.ceil((Date.parse(card.dataset.date + "T00:00:00Z") - now) / 864e5);
    var out = card.querySelector(".deadline-days");
    if (days < 0) { card.classList.add("passed"); out.textContent = "Passed"; }
    else { out.textContent = days === 0 ? "Today" : "In " + days + " day" + (days === 1 ? "" : "s"); }
    out.hidden = false;
  });
})();
</script>"""


def _bar(kind: str, label: str, values) -> str:
    buttons = "\n".join(
        f'  <button type="button" data-filter="{kind}" data-value="{v}" aria-pressed="{str(v == "all").lower()}">'
        f'{"All" if v == "all" else v}</button>'
        for v in ("all", *values)
    )
    return f'<div class="radar-filter note-filter" role="group" aria-label="{label}" hidden>\n{buttons}\n</div>'


def _status(st: str) -> str:
    return f'<span class="radar-tag status-{st.lower().replace(" ", "-")}">{st}</span>'


def _long_date(d: str) -> str:
    import datetime
    return datetime.date.fromisoformat(d).strftime("%-d %B %Y")


QUADRANT = {"India": 0, "EU": 1, "US": 2, "Canada": 2, "Global": 3}  # clockwise from the top right; North America shares a quadrant
RING = {3: 70, 2: 115, 1: 160, 0: 160}


def _legend() -> str:
    return "\n".join(
        f'    <li><span class="legend-dot status-{st.lower().replace(" ", "-")}"></span>{st}</li>' for st in STATUSES
    )


def _scope(on) -> str:
    import math
    cx = cy = 200
    by_q = {i: [n for n in on if QUADRANT[n["region"]] == i] for i in sorted(set(QUADRANT.values()))}
    blips = []
    for i, items in by_q.items():
        start = -90 + 90 * i
        for i, n in enumerate(items):
            angle = math.radians(start + 90 * (i + 1) / (len(items) + 1))
            r = RING[n["criticality"]]
            x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
            st = n["status"].lower().replace(" ", "-")
            blips.append(
                f'  <a href="/notes/{n["file"]}" aria-label="{html.escape(n["title"], quote=True)}">'
                f'<circle class="blip status-{st}" cx="{x:.1f}" cy="{y:.1f}" r="7"><title>{html.escape(n["title"])}</title></circle></a>'
            )
    labels = (
        '  <text x="372" y="34" text-anchor="end">India</text>\n'
        '  <text x="28" y="34">EU</text>\n'
        '  <text x="28" y="360">Canada</text>\n'
        '  <text x="28" y="378">US</text>\n'
        '  <text x="372" y="378" text-anchor="end">Global</text>'
    )
    blip_rows = "\n".join(blips)
    return f"""<svg class="radar-scope" viewBox="0 0 400 400" role="img" aria-label="Radar of every item, by region; closer to the centre needs action sooner">
  <defs><linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="currentColor" stop-opacity="0"/><stop offset="1" stop-color="currentColor" stop-opacity=".28"/></linearGradient></defs>
  <circle class="ring" cx="200" cy="200" r="160"/><circle class="ring" cx="200" cy="200" r="115"/><circle class="ring" cx="200" cy="200" r="70"/>
  <line class="ring" x1="200" y1="30" x2="200" y2="370"/><line class="ring" x1="30" y1="200" x2="370" y2="200"/>
  <g class="sweep"><path d="M200 200 L200 40 A160 160 0 0 1 338.6 120 Z" fill="url(#sweep)"/></g>
{labels}
{blip_rows}
</svg>"""


def build_radar() -> str:
    on = [n for n in notes() if n["region"]]
    updated = max(max(n["date"], n["reviewed"]) for n in on)
    cards = "\n".join(
        f'  <li class="deadline-card" data-date="{n["deadline"]}">\n'
        f'    <p class="deadline-date"><time datetime="{n["deadline"]}">{_long_date(n["deadline"])}</time>'
        f' <span class="deadline-days" hidden></span></p>\n'
        f'    <p><span class="radar-tag">{n["region"]}</span> {_status(n["status"])}</p>\n'
        f'    <a href="/notes/{n["file"]}">{html.escape(n["title"])}</a>\n'
        f'  </li>'
        for n in sorted((n for n in on if n["deadline"]), key=lambda n: n["deadline"])
    )
    urgent = "\n".join(
        f'  <p><a href="/notes/{n["file"]}">{html.escape(n["title"])}</a> '
        f'<span class="radar-tag">{n["region"]}</span> {_status(n["status"])}</p>\n'
        f'  <p class="radar-means">If your agent moves money: {html.escape(n["means"])}</p>'
        for n in on if n["criticality"] == 3
    )
    items = "\n".join(
        f'  <li data-region="{n["region"]}" data-status="{n["status"]}" data-criticality="{n["criticality"]}">\n'
        f'    <span class="radar-tag">{n["region"]}</span> {_status(n["status"])}{_badge(n["criticality"])}\n'
        f'    <a href="/notes/{n["file"]}">{html.escape(n["title"])}</a>\n'
        f'    <p>{html.escape(n["summary"])}</p>\n'
        f'    <p class="radar-means">If your agent moves money: {html.escape(n["means"])}</p>\n'
        f'    <p class="note-meta">Source published: <time class="source" datetime="{n["source_date"]}">{n["source_date"]}</time></p>\n'
        f'  </li>'
        for n in on
    )
    desc = ("What regulators, supervisors, banks and payment networks are saying and doing about AI agents "
            "that act on people's money, by region and status, newest source first.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/brand/actaseal-favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<title>AI agents and money: the radar &middot; ActaSeal</title>
<link rel="stylesheet" href="../css/base.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ActaSeal">
<meta property="og:title" content="AI agents and money: the radar">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="https://actaseal.com/radar/">
<meta property="og:image" content="https://actaseal.com/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="AI agents and money: the radar">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="https://actaseal.com/og-image.png">
<meta name="description" content="{desc}">
</head>
<body>
<main class="wrap radar">
<p class="radar-kicker">Radar &middot; Last updated: <time datetime="{updated}">{updated}</time> &middot; {len(on)} items</p>
<h1>AI agents and money: the radar</h1>
<p class="lede">{desc}</p>
<div class="radar-hero">
{_scope(on)}
<div class="radar-legend">
  <p>Each dot is one item. Tap a dot to read it.</p>
  <p><strong>Distance from the centre</strong>: inner ring, act now; middle, prepare; outer, watch.</p>
  <ul class="legend-status">
{_legend()}
  </ul>
</div>
</div>
<p class="radar-method">Only public sources that can be cited. Each item links to a short note and its source.
Added when something material happens, not on a schedule.</p>

<section class="act-now-box">
  <h2>Needs attention now</h2>
{urgent}
</section>

<h2>Dates to know</h2>
<ol class="deadline-cards">
{cards}
</ol>

<h2>Everything on the radar</h2>
{_bar("region", "Filter by region", REGIONS)}
{_bar("status", "Filter by status", STATUSES)}
<p class="note-filter-help">{STATUS_HELP}</p>
<ul class="note-list radar-list">
{items}
</ul>
<p class="radar-empty" hidden>Nothing on the radar for that combination yet.</p>

<section class="radar-bridge">
  <p>Across all of these, the question is the same: when your agent moved money, can you show what it did,
  in a form someone outside your company can check?</p>
  <div class="cta-row">
    <a class="cta-secondary" href="/refunds/">Start with a refund audit</a>
    <a class="cta-secondary" href="https://cal.com/actaseal/20min">Book a 20-min call</a>
  </div>
</section>

<p class="note-meta">A reading of public sources, not legal advice. <a href="/notes/">All notes</a> &middot; <a href="/">actaseal.com</a></p>
</main>
{RADAR_SCRIPT}
</body>
</html>
"""


if __name__ == "__main__":
    (ROOT / "radar").mkdir(exist_ok=True)
    (ROOT / "radar" / "index.html").write_text(build_radar(), encoding="utf-8")
    (NOTES / "index.html").write_text(build(), encoding="utf-8")
    print(f"notes/index.html: {len(notes())} note(s)")
