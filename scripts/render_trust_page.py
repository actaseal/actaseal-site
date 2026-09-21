"""Renders trust/bundle/trust-center-bundle.json into trust/index.html:
SBOM summary, the drill receipts present in the bundle, the CUEC
declaration, and a freshness verdict (how old generated_at is right now).
No dependency-free-renderer constraint here -- this is our own static site
build step, not an npm package -- but it still writes plain HTML, no CDN."""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DIR = REPO_ROOT / "trust" / "bundle"
BUNDLE_PATH = BUNDLE_DIR / "trust-center-bundle.json"

FRESHNESS_STALE_AFTER_DAYS = 90

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Trust -- ActaSeal</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="../favicon.ico">
<link rel="stylesheet" href="../css/base.css">
</head>
<body>
<header class="site-head">
  <div class="wrap">
    <div class="wordmark"><a href="/" style="text-decoration:none;color:inherit;">ActaSeal<span class="dot">.</span></a></div>
    <nav class="site-nav">
      <ul>
        <li><a href="/docs/">Docs</a></li>
        <li><a href="/trust/">Trust</a></li>
        <li><a href="/changelog/">Changelog</a></li>
        <li><a href="https://verify.actaseal.com">Verifier</a></li>
      </ul>
    </nav>
  </div>
</header>
<main class="wrap">
"""

TAIL = """
</main>
<footer class="site-foot"><div class="wrap">ActaSeal</div></footer>
</body>
</html>
"""


def freshness_verdict(generated_at_iso: str) -> str:
    generated_at = datetime.fromisoformat(generated_at_iso)
    age_days = (datetime.now(timezone.utc) - generated_at).days
    status = "FRESH" if age_days < FRESHNESS_STALE_AFTER_DAYS else "STALE"
    return f"{status} -- generated {age_days} day(s) ago ({html.escape(generated_at_iso)})"


def render(bundle: dict) -> str:
    payload = bundle["payload"]
    parts = [HEAD]
    parts.append("<section>")
    parts.append("<h1>Trust</h1>")
    parts.append(
        '<p class="lede">This page is rendered directly from a signed trust-center bundle -- '
        "produced by <code>actaseal trust-center bundle</code>, the same command any customer "
        "can run against their own deployment.</p>"
    )
    parts.append('<table class="dense">')
    parts.append(
        f"<tr><th>Bundle digest</th><td class=\"hash\">{html.escape(payload['bundle_hash'])}</td></tr>"
    )
    parts.append(f"<tr><th>Generated at</th><td>{html.escape(payload['generated_at'])}</td></tr>")
    parts.append(f"<tr><th>Freshness</th><td>{freshness_verdict(payload['generated_at'])}</td></tr>")
    parts.append(
        f"<tr><th>Signer public key</th><td class=\"hash\">{html.escape(bundle['signer_public_key_hex'])}</td></tr>"
    )
    parts.append("</table>")
    parts.append(
        '<p><a href="bundle/trust-center-bundle.json">Download the raw signed bundle</a> -- '
        "verify the signature yourself with the public key above.</p>"
    )
    parts.append("</section>")

    parts.append('<section id="sbom">')
    parts.append("<h2>SBOM</h2>")
    if payload.get("sbom_present"):
        components = payload["sbom"].get("components", [])
        parts.append(f"<p>{len(components)} component(s) declared.</p>")
    else:
        parts.append(
            "<p>Not embedded in this bundle -- generate one with "
            "<code>actaseal trust-center bundle --generate-sbom</code>.</p>"
        )
    parts.append("</section>")

    parts.append('<section id="drills">')
    parts.append("<h2>Resilience drill receipts</h2>")
    parts.append('<table class="dense"><tr><th>Drill</th><th>Result</th></tr>')
    for name, receipt in payload["drill_receipts"].items():
        if receipt is None:
            row = "not included in this bundle"
        else:
            detected = receipt["payload"].get("all_detected")
            row = "PASS -- all injected faults detected" if detected else "see raw payload"
        parts.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(str(row))}</td></tr>")
    parts.append("</table>")
    parts.append("</section>")

    parts.append('<section id="cuec">')
    parts.append("<h2>CUEC declaration</h2>")
    parts.append(
        "<p>Complementary user-entity controls -- derived from code, not written prose.</p>"
    )
    parts.append('<table class="dense"><tr><th>Control</th><th>Statement</th><th>Verified from</th></tr>')
    for control in payload["cuec_declaration"]["controls"]:
        parts.append(
            f"<tr><td>{html.escape(control.get('control',''))}</td>"
            f"<td>{html.escape(control.get('statement',''))}</td>"
            f"<td class=\"hash\">{html.escape(control.get('verified_from',''))}</td></tr>"
        )
    parts.append("</table>")
    parts.append("</section>")

    parts.append('<section id="questionnaires">')
    parts.append("<h2>Security questionnaires</h2>")
    parts.append(
        "<ul>"
        '<li><a href="bundle/caiq-lite.json">CAIQ-Lite (JSON)</a> / '
        '<a href="bundle/caiq-lite.csv">CAIQ-Lite (CSV)</a></li>'
        '<li><a href="bundle/sig-lite.json">SIG-Lite (JSON)</a> / '
        '<a href="bundle/sig-lite.csv">SIG-Lite (CSV)</a></li>'
        "</ul>"
    )
    parts.append("</section>")

    parts.append(TAIL)
    return "\n".join(parts)


def main() -> int:
    if not BUNDLE_PATH.exists():
        print(f"bundle not found: {BUNDLE_PATH}", file=sys.stderr)
        return 1
    bundle = json.loads(BUNDLE_PATH.read_text())
    out_path = REPO_ROOT / "trust" / "index.html"
    out_path.write_text(render(bundle))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
