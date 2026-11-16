"""The agent-order dispute check: the page exists, sends nothing, makes no
claim about card network rules, and its result matches the ticked boxes."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "agent-orders" / "index.html"


def _script() -> str:
    return re.search(r"<script>(.*?)</script>", PAGE.read_text(encoding="utf-8"), re.S).group(1)


def test_page_is_listed_for_answer_engines_and_sitemap():
    assert PAGE.is_file()
    assert "https://actaseal.com/agent-orders/" in (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert "https://actaseal.com/agent-orders/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_page_sends_nothing_and_loads_nothing_external():
    raw = PAGE.read_text(encoding="utf-8")
    js = _script()
    for word in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "localStorage", "document.cookie"):
        assert word not in js
    assert not re.search(r'<script[^>]+src=', raw)
    assert 'action=' not in raw


def test_page_says_it_is_not_a_card_network_rule():
    raw = PAGE.read_text(encoding="utf-8")
    assert "not a card network rule" in raw
    assert "not legal advice" in raw


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_result_matches_ticked_boxes():
    harness = (
        "var window={},document={getElementById:function(){return{addEventListener:function(){}}}};"
        + _script()
        + ";console.log(JSON.stringify([window.actasealAgentCheck([]),"
        "window.actasealAgentCheck(['allowed','limit','window','agent','order','confirm','delivery','fixed']),"
        "window.actasealAgentCheck(['delivery','confirm'])]))"
    )
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True).stdout
    none, everything, delivery_only = json.loads(out)
    assert len(none) == 4 and all(r["missing"] for r in none)
    assert all(r["missing"] == [] for r in everything)
    by_claim = {r["claim"]: r["missing"] for r in delivery_only}
    assert by_claim["It never arrived."] == []
    assert by_claim["The agent spent more than I allowed."] == ["limit", "order", "fixed"]
