"""Fail-closed link checker for actaseal-site.

Walks every .html file under the repo root. For each <a href> / <link href> /
<img src>:
  - a fragment-only link (#id) must resolve to an element with that id
    somewhere in the same page.
  - an internal link (starts with "/" or is relative, no scheme) must resolve
    to a real file on disk once directory-index and #fragment rules are
    applied.
  - an external link (http:// or https://, or mailto:) must appear in
    ALLOWED_EXTERNAL below, verbatim or as a mailto: prefix. Anything else
    fails closed -- an unrecognised external host is a bug, not something to
    silently allow.

Exits non-zero and prints every violation if any link fails. This mirrors
CLAUDE.md's "fail closed" house style: an unmatched case is a failure, not a
skip.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_EXTERNAL_PREFIXES = (
    "https://verify.actaseal.com",
    "https://github.com/actaseal/actaseal-verify",
    "https://github.com/ietf-wg-scitt/draft-ietf-scitt-architecture/issues/461",
    "https://github.com/ietf-wg-scitt/draft-ietf-scitt-architecture/issues/462",
    "https://github.com/legal-context-protocol/legal-context-protocol/pull/4",
    "https://github.com/shunhe-wang/agentic-resolution-interop/pull/22",
    "mailto:sales@actaseal.com",
)

HREF_RE = re.compile(r'''(?:href|src)=["']([^"'#][^"']*|#[^"']*)["']''')
ID_RE = re.compile(r'''\bid=["']([^"']+)["']''')


def find_html_files() -> list[Path]:
    return sorted(REPO_ROOT.rglob("*.html"))


def resolve_internal(link: str, source: Path) -> bool:
    """Resolve a same-repo link (no scheme) to a file on disk."""
    path_part = link.split("#", 1)[0]
    if not path_part:
        return True  # pure fragment, checked separately
    if path_part.startswith("/"):
        candidate = REPO_ROOT / path_part.lstrip("/")
    else:
        candidate = (source.parent / path_part).resolve()
    if candidate.is_dir():
        candidate = candidate / "index.html"
    if candidate.suffix == "" and not candidate.exists():
        # directory-style link with no trailing slash, e.g. "/docs"
        alt = candidate / "index.html"
        if alt.exists():
            return True
    return candidate.exists()


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    ids_in_page = set(ID_RE.findall(text))
    errors = []
    for link in HREF_RE.findall(text):
        if link.startswith("#"):
            frag = link[1:]
            if frag and frag not in ids_in_page:
                errors.append(f"{path}: broken same-page fragment #{frag}")
            continue
        if link.startswith("mailto:"):
            if not any(link.startswith(p) for p in ALLOWED_EXTERNAL_PREFIXES):
                errors.append(f"{path}: mailto link not in allowlist: {link}")
            continue
        if link.startswith("http://") or link.startswith("https://"):
            if not any(link.startswith(p) for p in ALLOWED_EXTERNAL_PREFIXES):
                errors.append(f"{path}: external link not in allowlist: {link}")
            continue
        if not resolve_internal(link, path):
            errors.append(f"{path}: dead internal link: {link}")
    return errors


def main() -> int:
    all_errors: list[str] = []
    for html_file in find_html_files():
        all_errors.extend(check_file(html_file))
    if all_errors:
        print(f"{len(all_errors)} link error(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"OK -- checked {len(find_html_files())} HTML file(s), all links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
