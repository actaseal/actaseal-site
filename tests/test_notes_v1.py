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
        assert "Xavier Goshi" in s or "&middot; ActaSeal &middot;" in s, f"{n['file']}: no author line"


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


# --- "Last reviewed": a note says how recently it was checked ---------------

def _reviewed(source: str):
    return re.search(r'Last reviewed: <time class="reviewed" datetime="(\d{4}-\d{2}-\d{2})"', source)


def test_every_note_says_when_it_was_last_reviewed():
    import datetime

    today = datetime.date.today().isoformat()
    for n in gen_notes.notes():
        s = (ROOT / "notes" / n["file"]).read_text(encoding="utf-8")
        reviewed = _reviewed(s)
        assert reviewed, f"{n['file']}: no 'Last reviewed' line"
        # a review cannot predate the note or lie in the future
        assert n["date"] <= reviewed.group(1) <= today, n["file"]


def test_index_shows_each_notes_review_date():
    index = (ROOT / "notes" / "index.html").read_text(encoding="utf-8")
    for n in gen_notes.notes():
        s = (ROOT / "notes" / n["file"]).read_text(encoding="utf-8")
        assert f'Last reviewed: <time class="reviewed" datetime="{_reviewed(s).group(1)}"' in index, n["file"]


def test_last_reviewed_is_never_later_than_the_notes_last_commit():
    """A review date is a claim that someone read the note against the
    product on that day. It cannot be later than the last time the note
    itself was committed: moving the date means committing the note."""
    import subprocess

    for n in gen_notes.notes():
        path = ROOT / "notes" / n["file"]
        last_commit = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path.relative_to(ROOT))],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.strip()
        if not last_commit:
            continue  # not a git checkout, or a note not yet committed: nothing to compare against
        reviewed = _reviewed(path.read_text(encoding="utf-8")).group(1)
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", str(path.relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        if dirty:
            continue  # being edited right now; the date is checked once it is committed
        assert reviewed <= last_commit, f"{n['file']}: reviewed {reviewed} is after its last commit {last_commit}"
