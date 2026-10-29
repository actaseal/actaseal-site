"""What an AI assistant reads when someone asks it for this kind of product.

People ask ChatGPT, Gemini, Claude or Perplexity things like "how do I stop our AI support
agent refunding above policy?". Those assistants read llms.txt, structured data and plain
question-and-answer text. So the site says, in the words people ask with, who ActaSeal is
for and what problem it answers, and the structured data repeats only what the page shows.
Outcomes only: no price, no architecture, no roadmap.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def ld_blocks(src):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', src, re.S)]


def visible(src):
    src = re.sub(r"<(script|style)\b.*?</\1>", " ", src, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", src))).strip()


def test_llms_txt_says_who_it_is_for_and_what_to_start_with():
    llms = page("llms.txt")
    for phrase in ("refunds", "payouts", "D2C", "quick commerce", "fintech", "refund audit",
                   "https://actaseal.com/refunds/", "https://actaseal.com/pilot/"):
        assert phrase in llms, phrase
    assert "Policy gateway" not in llms


def test_the_only_script_on_the_homepage_is_structured_data():
    src = page("index.html")
    assert re.sub(r'<script type="application/ld\+json">.*?</script>', "", src, flags=re.S).lower().count("<script") == 0
    kinds = {b["@type"] for b in ld_blocks(src)}
    assert {"Organization", "SoftwareApplication"} <= kinds


def test_the_refund_page_answers_the_questions_people_ask_and_the_faq_data_matches_the_page():
    src = page("refunds/index.html")
    faq = next(b for b in ld_blocks(src) if b["@type"] == "FAQPage")
    shown = visible(src)
    assert len(faq["mainEntity"]) >= 5
    for item in faq["mainEntity"]:
        assert item["name"] in shown, item["name"]
        assert item["acceptedAnswer"]["text"] in shown, item["name"]


def test_ai_crawlers_are_named_and_allowed():
    robots = page("robots.txt")
    for bot in ("GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {bot}\nAllow: /" in robots, bot
