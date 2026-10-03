"""render_trust_page.py renders a signed trust-center bundle (kept outside
this repository, shared under NDA) into an HTML page with the digest,
freshness verdict and CUEC controls -- and without internal references."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "render_trust_page.py"
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "trust_bundle_sample.json"
PUBLISHED = REPO_ROOT / "trust" / "index.html"


def test_render_includes_digest_freshness_and_cuec(tmp_path):
    out = tmp_path / "trust.html"
    result = subprocess.run([sys.executable, str(SCRIPT), str(SAMPLE), str(out)],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    bundle = json.loads(SAMPLE.read_text())
    page = out.read_text()
    assert bundle["payload"]["bundle_hash"] in page
    assert bundle["payload"]["generated_at"] in page
    assert "FRESH" in page or "STALE" in page
    for control in bundle["payload"]["cuec_declaration"]["controls"]:
        assert control["control"] in page
        assert control["verified_from"] not in page


def test_render_requires_a_bundle_path():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 2


def test_published_page_does_not_link_nda_material():
    page = PUBLISHED.read_text()
    assert "bundle/" not in page
    assert "caiq-lite" not in page and "sig-lite" not in page
    assert not (REPO_ROOT / "trust" / "bundle").exists()
