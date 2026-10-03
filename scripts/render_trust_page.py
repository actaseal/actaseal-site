"""Renders a signed trust-center bundle into trust/index.html: digest,
freshness verdict, drill results and the CUEC controls.

The bundle itself is not published (it is shared under NDA), so it is
passed in from outside this repository:

    python scripts/render_trust_page.py <trust-center-bundle.json> [out.html]
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "trust" / "index.html"
NDA_CONTACT = '<a href="mailto:sales@actaseal.com">sales@actaseal.com</a>'

FRESHNESS_STALE_AFTER_DAYS = 90

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Trust -- ActaSeal</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="../favicon.ico">
<link rel="stylesheet" href="../css/base.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ActaSeal">
<meta property="og:title" content="ActaSeal trust centre">
<meta property="og:description" content="Rendered from a signed trust-centre bundle produced by the same command any customer can run against their own deployment.">
<meta property="og:url" content="https://actaseal.com/trust/">
<meta property="og:image" content="https://actaseal.com/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="ActaSeal trust centre">
<meta name="twitter:description" content="Rendered from a signed trust-centre bundle produced by the same command any customer can run against their own deployment.">
<meta name="twitter:image" content="https://actaseal.com/og-image.png">
<meta name="description" content="Rendered from a signed trust-centre bundle produced by the same command any customer can run against their own deployment.">
</head>
<body>
<header class="site-head">
  <div class="wrap">
    <div class="wordmark"><a href="/" style="text-decoration:none;color:inherit;">ActaSeal<span class="dot">.</span></a></div>
    <nav class="site-nav">
      <ul>
        <li><a href="/as1215/">AS 1215</a></li>
        <li><a href="https://verify.actaseal.com/browser/">Verify</a></li>
        <li><a href="https://cbom.actaseal.com">CBOM Check</a></li>
        <li><a href="/trust/">Trust</a></li>
        <li><a href="/docs/">Docs</a></li>
        <li><a href="mailto:sales@actaseal.com">Contact</a></li>
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
        '<p class="lede">This page is rendered from a signed trust-center bundle, '
        "produced by the same command any customer can run against their own deployment.</p>"
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
        f"<p>The full signed bundle is available under NDA from {NDA_CONTACT}. "
        "Check its digest and signature against the values above.</p>"
    )
    parts.append("</section>")

    parts.append('<section id="sbom">')
    parts.append("<h2>SBOM</h2>")
    if payload.get("sbom_present"):
        components = payload["sbom"].get("components", [])
        parts.append(f"<p>{len(components)} component(s) declared.</p>")
    else:
        parts.append("<p>Not embedded in this bundle.</p>")
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
        "<p>Complementary user-entity controls: what the operator of a deployment is responsible for.</p>"
    )
    parts.append('<table class="dense"><tr><th>Control</th><th>Statement</th></tr>')
    for control in payload["cuec_declaration"]["controls"]:
        parts.append(
            f"<tr><td>{html.escape(control.get('control',''))}</td>"
            f"<td>{html.escape(control.get('statement',''))}</td></tr>"
        )
    parts.append("</table>")
    parts.append("</section>")

    parts.append('<section id="questionnaires">')
    parts.append("<h2>Security questionnaires</h2>")
    parts.append(
        "<p>Completed CAIQ-Lite and SIG-Lite questionnaires are available under NDA from "
        f"{NDA_CONTACT}.</p>"
    )
    parts.append("</section>")

    parts.append(TAIL)
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    bundle_path = Path(argv[1])
    if not bundle_path.exists():
        print(f"bundle not found: {bundle_path}", file=sys.stderr)
        return 1
    bundle = json.loads(bundle_path.read_text())
    out_path = Path(argv[2]) if len(argv) == 3 else DEFAULT_OUT
    out_path.write_text(render(bundle))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
