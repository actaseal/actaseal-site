"""Renders an openapi.json (produced by active_code's
scripts/export_openapi.py) into a single dependency-free static HTML page
under docs/api/index.html. No CDN, no JS framework -- plain tables."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

METHOD_ORDER = ["get", "post", "put", "patch", "delete"]

PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>API reference -- ActaSeal</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="../../favicon.ico">
<link rel="stylesheet" href="../../css/base.css">
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
<h1>API reference</h1>
<p class="lede">Generated from the live FastAPI app's own OpenAPI schema
(<code>scripts/export_openapi.py</code> in the private repo) -- every route
below is a route that actually exists, not hand-maintained documentation
that can drift.</p>
"""

PAGE_TAIL = """
</main>
<footer class="site-foot"><div class="wrap">ActaSeal</div></footer>
</body>
</html>
"""


def render(schema: dict) -> str:
    parts = [PAGE_HEAD]
    paths = schema.get("paths", {})
    for path in sorted(paths):
        item = paths[path]
        for method in METHOD_ORDER:
            if method not in item:
                continue
            op = item[method]
            anchor = html.escape(f"{method}-{path}".replace("/", "-").strip("-"))
            summary = html.escape(op.get("summary") or op.get("operationId", ""))
            parts.append(f'<section id="{anchor}">')
            parts.append(
                f'<h3><span class="hash">{method.upper()}</span> '
                f'<code>{html.escape(path)}</code></h3>'
            )
            if summary:
                parts.append(f"<p>{summary}</p>")
            params = op.get("parameters", [])
            if params:
                parts.append('<table class="dense"><caption>Parameters</caption>')
                parts.append("<tr><th>Name</th><th>In</th><th>Required</th></tr>")
                for p in params:
                    parts.append(
                        f"<tr><td>{html.escape(p.get('name',''))}</td>"
                        f"<td>{html.escape(p.get('in',''))}</td>"
                        f"<td>{'yes' if p.get('required') else 'no'}</td></tr>"
                    )
                parts.append("</table>")
            responses = op.get("responses", {})
            if responses:
                parts.append('<table class="dense"><caption>Responses</caption>')
                parts.append("<tr><th>Status</th><th>Description</th></tr>")
                for status, resp in sorted(responses.items()):
                    parts.append(
                        f"<tr><td>{html.escape(status)}</td>"
                        f"<td>{html.escape(resp.get('description',''))}</td></tr>"
                    )
                parts.append("</table>")
            parts.append("</section>")
    parts.append(PAGE_TAIL)
    return "\n".join(parts)


def main() -> int:
    schema_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT.parent / "active_code" / "openapi.json"
    if not schema_path.exists():
        print(f"schema not found: {schema_path}", file=sys.stderr)
        return 1
    schema = json.loads(schema_path.read_text())
    out_dir = Path.cwd() / "docs" / "api"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(render(schema))
    print(f"wrote {out_path} ({len(schema.get('paths', {}))} routes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
