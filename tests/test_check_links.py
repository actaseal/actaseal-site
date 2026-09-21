"""Proves scripts/check_links.py actually fails on a broken link, and that
the real site (index.html, docs/, trust/, changelog/) currently passes."""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_links.py"


def run_checker(cwd: Path, script: Path = CHECKER) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_real_site_passes():
    result = run_checker(REPO_ROOT)
    assert result.returncode == 0, result.stderr


def test_dead_internal_link_fails_closed(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_links.py").write_text(CHECKER.read_text())
    (tmp_path / "index.html").write_text(
        '<a href="/nowhere/real.html">dead link</a>'
    )
    result = run_checker(tmp_path, tmp_path / "scripts" / "check_links.py")
    assert result.returncode == 1
    assert "dead internal link" in result.stderr


def test_unlisted_external_link_fails_closed(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_links.py").write_text(CHECKER.read_text())
    (tmp_path / "index.html").write_text(
        '<a href="https://example.com/not-allowlisted">bad</a>'
    )
    result = run_checker(tmp_path, tmp_path / "scripts" / "check_links.py")
    assert result.returncode == 1
    assert "not in allowlist" in result.stderr


def test_broken_fragment_fails_closed(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_links.py").write_text(CHECKER.read_text())
    (tmp_path / "index.html").write_text('<a href="#nope">bad anchor</a>')
    result = run_checker(tmp_path, tmp_path / "scripts" / "check_links.py")
    assert result.returncode == 1
    assert "broken same-page fragment" in result.stderr
