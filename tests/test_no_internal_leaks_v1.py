"""Nothing a visitor can read on this site describes how the product is
built, sold or staffed. Outcomes only.

Checked on the visible text of every published page (and security.txt):
no source paths or file names, no internal document names, no tiers,
metering limits or discount terms, no statements about company size or
stage, and no scores or percentages.
"""
import html
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {"tests", "scripts", ".git", "node_modules", ".hypothesis"}

# The standalone verifier is public and is run by file name; these are the
# only source file names a visitor is told to use.
VERIFIER_FILES = {"verify.py", "verify_receipt.py", "verify_seal.py"}

# The generated API reference lists what the API accepts; it is checked
# for the same things except code-shaped tokens inside schema names.
PATTERNS = [
    ("source path", re.compile(r"(?<![@/.\w])actaseal/[\w/]+")),
    ("module path", re.compile(r"\bactaseal\.(?!com\b|sdk\b|mcp\b)[a-z_]+\.[a-z_]+")),
    ("internal document", re.compile(r"CLAUDE\.md|README-DEPLOY|USER_ACTIONS|STATE\.md|KNOWN_FAILURES|CAPABILITIES\.md", re.I)),
    ("internal path", re.compile(r"(?<![\w/.-])(?:docs|scripts|tests)/[\w./-]+")),
    ("config file", re.compile(r"\b[\w-]+\.(?:ya?ml|toml|ini)\b")),
    ("markdown file", re.compile(r"\b[\w-]+\.md\b")),
    ("tier with price", re.compile(r"\b(Foundation|Firm|Enterprise|Starter|Pro|Team)\b[^.]{0,80}[$₹€£]\s?\d", re.I)),
    ("price", re.compile(r"[$₹€£]\s?\d[\d,]{2,}")),
    ("metering limit", re.compile(r"\bup to \d+ (archived )?(engagements|agents|users|seats|actions)|per (archived )?engagement, per year|\b\d+ (archived )?engagements per year", re.I)),
    ("tier language", re.compile(r"\bfor your tier\b|\bat every tier\b|\btier table\b", re.I)),
    ("watermark", re.compile(r"watermark", re.I)),
    ("discount terms", re.compile(r"discount|early[- ]adopter|early deployer|first (three|few|\d+) (deployments|customers|firms)|design partner|founding customer", re.I)),
    ("company stage", re.compile(r"no customers|not in production|in production yet|one person|solo founder|single founder|small vendor|no committee", re.I)),
    ("score or percentage", re.compile(r"\b\d+(\.\d+)?\s?%|\bconfidence (score|level)\b|\b(risk|trust|readiness|quality) score\b", re.I)),
]


def _pages():
    for path in sorted(ROOT.rglob("*.html")):
        if SKIP_PARTS & set(path.relative_to(ROOT).parts):
            continue
        yield path
    yield ROOT / ".well-known" / "security.txt"


def _visible(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    if path.suffix != ".html":
        return raw
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S)
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    # text a visitor sees, plus the descriptions shown when a link is shared
    metas = " ".join(re.findall(r'<meta[^>]+content="([^"]*)"', raw))
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw) + " " + metas))


def _findings(path: Path) -> list[str]:
    text = _visible(path)
    found = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            found.append(f"{label}: {text[max(0, match.start() - 40):match.end() + 30].strip()!r}")
    for match in re.finditer(r"\b[\w/.-]*\w\.py\b", text):
        if match.group(0).split("/")[-1] not in VERIFIER_FILES or "/" in match.group(0).replace("../", ""):
            found.append(f"source file: {text[max(0, match.start() - 40):match.end() + 30].strip()!r}")
    return found


# Legal wording is not edited by this check's author: the licence terms
# say "the fees for your tier", and changing a contract term is a legal
# decision. Recorded here so the exception is visible, not silent.
LEGAL_WORDING_EXCEPTIONS = {"legal/terms.html": {"tier language"}}


@pytest.mark.parametrize("path", list(_pages()), ids=lambda p: str(p.relative_to(ROOT)))
def test_page_exposes_nothing_internal(path):
    allowed = LEGAL_WORDING_EXCEPTIONS.get(str(path.relative_to(ROOT)), set())
    found = [f for f in _findings(path) if f.split(":", 1)[0] not in allowed]
    assert not found, "\n".join(found)


def test_the_check_itself_catches_each_kind():
    samples = {
        "source path": "see actaseal/api/app.py for details",
        "module path": "handled by actaseal.gateway.runtime",
        "internal document": "as CLAUDE.md says",
        "internal path": "see docs/runbooks/key_compromise",
        "tier with price": "Firm tier is $48,000 a year",
        "metering limit": "up to 25 archived engagements",
        "watermark": "exports are watermarked",
        "discount terms": "an early-adopter rate",
        "company stage": "run by one person",
        "score or percentage": "a 97% match",
    }
    for label, sample in samples.items():
        pattern = dict(PATTERNS)[label]
        assert pattern.search(sample), label
    # documented public usage is not a finding
    for fine in ("python verify.py packet.zip", "from actaseal.sdk.thin_client import ActaSeal",
                 "python -m actaseal.mcp --config proxy.json", "security@actaseal.com", "verify.actaseal.com"):
        for _label, pattern in PATTERNS:
            assert not pattern.search(fine), (fine, _label)


# --- a route inventory must never be a public page --------------------------

ROUTE_LINE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/[\w{}./-]*")


def test_no_api_reference_page_or_generator_is_published():
    assert not (ROOT / "docs" / "api").exists(), "docs/api/ is a route inventory"
    for name in ("render_openapi.py", "openapi.json"):
        assert not list(p for p in ROOT.rglob(name) if ".git" not in p.parts), f"{name} would bring the page back"
    assert "/docs/api" not in (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    for path in _pages():
        if path.suffix == ".html":
            raw = path.read_text(encoding="utf-8")
            assert not re.search(r'href="(?:/docs/)?api/?"', raw), f"{path.relative_to(ROOT)} links to an API reference"


@pytest.mark.parametrize("path", list(_pages()), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_page_lists_routes(path):
    found = sorted({m.group(0) for m in ROUTE_LINE.finditer(_visible(path))})
    assert not found, f"route(s) listed: {found[:8]}"


def test_route_check_catches_an_inventory():
    assert ROUTE_LINE.search("GET /accounts/{account_id}/balance")
    assert ROUTE_LINE.search("POST /gateway/preflight")
    assert not ROUTE_LINE.search("Get it from the operator directly")
