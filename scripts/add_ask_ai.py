#!/usr/bin/env python3
"""Give every note a canonical URL and "Ask an AI about this page" links.

Idempotent: run after adding a note. tests/test_ask_ai_v1.py checks every note.
"""
import html
import pathlib
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
BASE = "https://actaseal.com/notes/"
FOOTER = '<p><a href="/notes/">All notes</a>'
ENGINES = (
    ("ChatGPT", "https://chatgpt.com/?q="),
    ("Claude", "https://claude.ai/new?q="),
    ("Perplexity", "https://www.perplexity.ai/search?q="),
)


def ask_block(url: str, title: str) -> str:
    prompt = f"Read {url} and answer: {title}"
    q = urllib.parse.quote(prompt, safe="")
    links = " &middot; ".join(
        f'<a href="{base}{q}" rel="noopener" target="_blank">{name}</a>' for name, base in ENGINES
    )
    return f'<p class="ask-ai">Ask an AI about this page: {links}</p>\n'


def apply(p: pathlib.Path) -> bool:
    s = p.read_text(encoding="utf-8")
    url = BASE + p.name
    title = html.unescape(re.search(r"<h1>(.*?)</h1>", s, re.S).group(1)).strip()
    out = s
    if 'rel="canonical"' not in out:
        out = out.replace("<title>", f'<link rel="canonical" href="{url}">\n<title>', 1)
    out = re.sub(r'<p class="ask-ai">.*?</p>\n', "", out)
    out = out.replace(FOOTER, ask_block(url, title) + FOOTER, 1)
    if out != s:
        p.write_text(out, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    changed = [p.name for p in sorted(NOTES.glob("*.html")) if p.name != "index.html" and apply(p)]
    print(f"updated {len(changed)} notes")
