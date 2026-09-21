"""render_trust_page.py must render the real signed bundle at
trust/bundle/trust-center-bundle.json into trust/index.html, including the
bundle digest, freshness verdict, and CUEC controls -- ONESHOT-FRONT F3."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "render_trust_page.py"
BUNDLE_PATH = REPO_ROOT / "trust" / "bundle" / "trust-center-bundle.json"


def test_real_bundle_exists_and_is_a_signed_payload():
    bundle = json.loads(BUNDLE_PATH.read_text())
    assert bundle["payload"]["schema_version"] == "trust_center_bundle.v1"
    assert bundle["signature_hex"]


def test_render_trust_page_includes_digest_and_freshness_and_cuec():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    bundle = json.loads(BUNDLE_PATH.read_text())
    html = (REPO_ROOT / "trust" / "index.html").read_text()
    assert bundle["payload"]["bundle_hash"] in html
    assert bundle["payload"]["generated_at"] in html
    assert "FRESH" in html or "STALE" in html
    for control in bundle["payload"]["cuec_declaration"]["controls"]:
        assert control["control"] in html
