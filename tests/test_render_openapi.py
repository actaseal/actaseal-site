"""render_openapi.py must produce a dependency-free static HTML page from a
real openapi.json -- no CDN scripts, no external stylesheet other than our
own css/base.css."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "render_openapi.py"

FAKE_SCHEMA = {
    "openapi": "3.1.0",
    "paths": {
        "/gateway/preflight": {
            "post": {
                "summary": "Preflight a gated action",
                "parameters": [],
                "responses": {"200": {"description": "Decision"}},
            }
        }
    },
}


def test_render_openapi_no_cdn_no_framework(tmp_path):
    schema_path = tmp_path / "openapi.json"
    schema_path.write_text(json.dumps(FAKE_SCHEMA))
    out_dir = tmp_path / "site"
    out_dir.mkdir()
    (out_dir / "docs").mkdir()
    (out_dir / "css").mkdir()
    (out_dir / "css" / "base.css").write_text("body{}")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(schema_path)],
        cwd=out_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    html = (out_dir / "docs" / "api" / "index.html").read_text()
    assert "/gateway/preflight" in html
    assert "POST" in html
    assert "cdn." not in html.lower()
    assert "<script" not in html.lower()
