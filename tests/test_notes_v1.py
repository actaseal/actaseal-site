"""Notes must carry a date and an author, and the index must match the files."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gen_notes  # noqa: E402


def test_every_note_has_a_date_and_an_author():
    for n in gen_notes.notes():
        s = (ROOT / "notes" / n["file"]).read_text(encoding="utf-8")
        assert re.search(r'<time datetime="\d{4}-\d{2}-\d{2}"', s), n["file"]
        assert "Xavier Goshi" in s, f"{n['file']}: no author line"


def test_index_lists_exactly_the_notes_present():
    index = (ROOT / "notes" / "index.html").read_text(encoding="utf-8")
    files = {n["file"] for n in gen_notes.notes()}
    listed = set(re.findall(r'<a href="([^"/]+\.html)"', index))
    assert files == listed, f"index/files mismatch: only in files {files - listed}, only in index {listed - files}"


def test_index_is_current():
    assert gen_notes.build() == (ROOT / "notes" / "index.html").read_text(encoding="utf-8"), (
        "notes/index.html is stale -- run scripts/gen_notes.py"
    )


def test_no_cadence_promise():
    """A notes section that promises a schedule becomes a staleness marker."""
    index = (ROOT / "notes" / "index.html").read_text(encoding="utf-8")
    for word in ("weekly", "monthly", "every week", "every month", "subscribe", "newsletter"):
        assert word not in index.lower(), f"index promises a cadence: {word}"
