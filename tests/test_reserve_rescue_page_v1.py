"""The payout-hold appeal builder: the page exists, sends nothing, never puts
typed text into the page as HTML, says Shopify decides, and its numbers and
letter match the facts typed in."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "reserve-rescue" / "index.html"
URL = "https://actaseal.com/reserve-rescue/"


def _script() -> str:
    return re.search(r"<script>(.*?)</script>", PAGE.read_text(encoding="utf-8"), re.S).group(1)


def test_page_is_listed_for_answer_engines_and_sitemap():
    assert PAGE.is_file()
    assert URL in (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert URL in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_page_sends_nothing_and_loads_nothing_external():
    raw = PAGE.read_text(encoding="utf-8")
    js = _script()
    for word in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "localStorage",
                 "sessionStorage", "document.cookie", "indexedDB"):
        assert word not in js
    assert not re.search(r"<script[^>]+src=", raw)
    assert "action=" not in raw


def test_typed_text_is_never_written_as_html():
    js = _script()
    for word in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function("):
        assert word not in js


def test_page_says_who_decides_and_what_it_is_not():
    raw = PAGE.read_text(encoding="utf-8")
    assert "not affiliated with Shopify" in raw
    assert "not legal advice" in raw
    assert "Shopify decides" in raw


def _run(calls: str):
    harness = (
        "var window={},document={getElementById:function(){return{addEventListener:function(){}}}};"
        + _script()
        + ";var R=window.actasealReserve;console.log(JSON.stringify(" + calls + "))"
    )
    return json.loads(subprocess.run(["node", "-e", harness], capture_output=True,
                                     text=True, check=True).stdout)


FULL = {
    "store": "<img src=x onerror=alert(1)> Brand",
    "kind": "reserve", "started": "2026-04-08", "amount": "18000", "currency": "USD",
    "reservePct": "30", "holdDays": "90", "condition": "chargeback rate under 1 percent for 30 days",
    "conditionMet": "2026-05-11", "orders": "2500", "chargebacks": "10", "won": "4",
    "tracked": "2450", "cause": "card_testing", "causeNote": "", "fix": "Turned on bot protection.",
    "reasons": ["fraud", "not_received"],
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_numbers_match_the_facts():
    full, empty = _run("[R.compute(%s,'2026-05-28'),R.compute({},'2026-05-28')]" % json.dumps(FULL))
    assert full["rate"] == "0.40"
    assert full["tracked"] == "98.0"
    assert full["daysHeld"] == 50
    assert full["daysSinceMet"] == 17
    assert full["holdEnds"] == "2026-07-07"
    for key in ("rate", "tracked", "daysHeld", "daysSinceMet", "holdEnds"):
        assert empty[key] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_letter_uses_the_facts_and_never_prints_blanks():
    full, empty = _run("[R.letter(%s,'2026-05-28'),R.letter({},'2026-05-28')]" % json.dumps(FULL))
    for text in ("<img src=x onerror=alert(1)> Brand", "USD 18,000", "0.40", "2026-05-11",
                 "chargeback rate under 1 percent for 30 days", "card-testing", "Turned on bot protection."):
        assert text in full
    for letter in (full, empty):
        for bad in ("undefined", "NaN", "null", "Infinity"):
            assert bad not in letter
    assert "release" in empty.lower()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_letter_says_when_the_stated_hold_period_is_over():
    before, after = _run("[R.letter(%s,'2026-05-28'),R.letter(%s,'2026-07-17')]" % (json.dumps(FULL), json.dumps(FULL)))
    assert "ends on 2026-07-07." in before and "ended on" not in before
    assert "ended on 2026-07-07, 10 days ago, and the funds have not been released." in after


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_bad_numbers_are_ignored_not_printed():
    out = _run("[R.compute({orders:'0',chargebacks:'5',tracked:'-3',amount:'abc',started:'2026-13-45'},'2026-05-28'),"
               "R.compute({orders:'100',chargebacks:'500'},'2026-05-28')]")
    zero, more_than_orders = out
    assert zero["rate"] is None and zero["daysHeld"] is None and zero["amount"] is None
    assert more_than_orders["rate"] is None


def test_form_cannot_be_submitted_so_nothing_reaches_a_url():
    raw = PAGE.read_text(encoding="utf-8")
    assert 'type="submit"' not in raw
    assert re.search(r'<button type="button" id="rr-build">', raw)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_review_findings_stay_fixed():
    calls = ("[R.compute({amount:'99999999999999999999999',orders:'1000000000000000000000'},'2026-05-28'),"
             "R.letter({orders:'10.5',chargebacks:'20',won:'9'},'2026-05-28'),"
             "R.letter({orders:'10',chargebacks:'20'},'2026-05-28'),"
             "R.letter({conditionMet:'2026-05-01'},'2026-05-28'),"
             "R.letter({},'2026-05-28'),"
             "R.letter({reservePct:'0',condition:'x',conditionMet:'2026-05-27'},'2026-05-28'),"
             "R.plan({kind:'disabled'},'2026-05-28')]")
    big, decimal, more_cb, met_only, empty, small, disabled = _run(calls)
    assert big["amount"] is None and big["orders"] is None
    assert "10.5" not in decimal and "Orders:" not in decimal
    assert "Chargebacks: 20" not in more_cb
    assert "condition has been met" not in met_only
    assert "delivery confirmations" not in empty and "supplier invoices" not in empty
    assert "0 percent" not in small and "1 day ago" in small and "1 days" not in small
    assert "set out the reserve terms" not in disabled["follow"][0][1]
