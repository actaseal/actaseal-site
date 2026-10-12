"""The public docs page: no internal file names, no promise it cannot
keep about the TypeScript SDK, and snippets that match the real API."""
import html
import inspect
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = Path.home() / "a/active_code"
RAW = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
TEXT = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", RAW)))


def _section(section_id: str) -> str:
    return re.search(r'<section id="' + section_id + r'">.*?</section>', RAW, flags=re.S).group(0)


def test_no_internal_file_names_or_build_trivia():
    for pattern in (r"README", r"\.md\b", r"buildx", r"this repo\b", r"in the repo\b"):
        assert not re.search(pattern, TEXT), f"docs page still matches {pattern!r}"


def test_typescript_sdk_is_described_without_overpromising():
    low = TEXT.lower()
    assert "not published to npm" in low
    assert "on request" in low
    for phrase in ("we will send", "yet", "soon", "once it resolves"):
        assert phrase not in re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", _typescript()))).lower(), phrase


def _typescript() -> str:
    start = RAW.index("<h3>TypeScript</h3>")
    return RAW[start:RAW.index("<h3>", start + 10)]


def test_openai_agents_snippet_wraps_the_function_then_makes_the_tool():
    start = RAW.index("<h3>OpenAI Agents SDK</h3>")
    snippet = html.unescape(re.search(r"<pre[^>]*>(.*?)</pre>", RAW[start:], flags=re.S).group(1))
    assert "from agents import function_tool" in snippet
    guard_call = re.search(r"(\w+) = guard_openai_agents_tool\(\s*\w+,\s*(\w+)", snippet)
    assert guard_call, snippet
    guarded_name, wrapped = guard_call.groups()
    assert "tool" not in wrapped, "the adapter wraps the plain function, not a tool object"
    assert f"function_tool({guarded_name})" in snippet


def test_mcp_section_states_how_it_is_used_how_evidence_is_attached_and_its_limit():
    section = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", _section("mcp"))))
    assert "tools/call" in section
    assert "amount and currency" in section
    assert "com.actaseal/evidence" in section and "_meta" in section
    assert "never reaches the tool server" in section or "removes it before" in section
    assert "cannot attach evidence" not in section


def test_mcp_evidence_key_matches_the_product():
    if not (PRODUCT / "actaseal" / "mcp" / "proxy.py").is_file():
        pytest.skip("product repository is not checked out next to this one")
    source = (PRODUCT / "actaseal" / "mcp" / "proxy.py").read_text(encoding="utf-8")
    key = re.search(r'^EVIDENCE_META_KEY = "([^"]+)"', source, flags=re.M)
    assert key, "the MCP proxy no longer takes evidence: the docs say it does"
    assert key.group(1) in html.unescape(_section("mcp"))


def test_snippets_match_the_real_adapters():
    if not (PRODUCT / "actaseal" / "sdk").is_dir():
        pytest.skip("product repository is not checked out next to this one")
    sys.path.insert(0, str(PRODUCT))
    try:
        from actaseal.sdk.integrations import openai_agents_tools
        from actaseal.sdk.thin_client import ActaSeal
    finally:
        sys.path.remove(str(PRODUCT))
    params = list(inspect.signature(openai_agents_tools.guard_openai_agents_tool).parameters)
    assert params[:2] == ["actaseal", "func"] and "action_type" in params
    init = inspect.signature(ActaSeal.__init__).parameters
    for name in ("api_key", "policy_id", "policy_version"):
        assert name in init and f"{name}=" in html.unescape(_section("sdks")), name
    assert (PRODUCT / "actaseal" / "mcp" / "__main__.py").is_file(), "docs say `python -m actaseal.mcp`"
