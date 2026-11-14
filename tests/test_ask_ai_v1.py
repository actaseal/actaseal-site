import pathlib
import re
import urllib.parse

NOTES = pathlib.Path(__file__).resolve().parent.parent / "notes"


def note_files():
    return [p for p in sorted(NOTES.glob("*.html")) if p.name != "index.html"]


def test_every_note_has_canonical_and_ask_ai():
    for p in note_files():
        s = p.read_text(encoding="utf-8")
        url = f"https://actaseal.com/notes/{p.name}"
        assert f'<link rel="canonical" href="{url}">' in s, p.name
        block = re.search(r'<p class="ask-ai">(.*?)</p>', s)
        assert block, p.name
        for base in ("https://chatgpt.com/?q=", "https://claude.ai/new?q=", "https://www.perplexity.ai/search?q="):
            assert base in block.group(1), (p.name, base)
        assert urllib.parse.quote(url, safe="") in block.group(1), p.name
        assert s.count('class="ask-ai"') == 1, p.name
