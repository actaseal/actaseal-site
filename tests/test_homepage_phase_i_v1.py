"""Phase I of the website pass: banner, hero, three doors, CTA, footer for
humans and agents, nav by buyer task, two proof lines, standards section.

Every date on the page must be one marked VERIFIED in the product repo's
dates tracker; the other claims are checked against code in
test_site_claims_are_true.py.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"
NAV_PAGES = ["index.html", "as1215/index.html", "changelog/index.html", "docs/index.html",
             "legal/dpa.html", "legal/privacy.html", "legal/subprocessors.html", "legal/terms.html",
             "trust/index.html"]


def raw() -> str:
    return PAGE.read_text(encoding="utf-8")


def text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def block(pattern: str) -> str:
    m = re.search(pattern, raw(), flags=re.S)
    assert m, f"missing {pattern}"
    return m.group(0)


# I2 -- banner
def test_banner_says_verifier_live_and_gives_one_verified_deadline():
    banner = block(r'<div class="top-banner".*?</div>')
    t = text(banner)
    assert "Verifier live" in t
    assert "QC 1000" in t and "15 December 2026" in t
    assert re.search(r'href="https://pcaobus\.org/news-events/news-releases/[^"]+"', banner)
    assert raw().index("top-banner") < raw().index("<header")


def test_no_unverified_or_eu_high_risk_dates_on_the_page():
    t = text(raw())
    assert "AI Act" not in t
    assert "2 August 2026" not in t and "2 December 2027" not in t
    dates = set(re.findall(r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\b", t))
    assert dates <= {"15 December 2026"}, dates


# I1 -- hero
def test_hero_has_the_enemy_line_and_the_differentiator():
    hero = text(block(r'<section id="what">.*?</section>'))
    assert "Your agent's logs are your own testimony." in hero
    assert "before it runs" in hero
    assert "without trusting us" in hero


# I3 -- three doors
def test_three_doors_each_link_somewhere_real():
    doors = block(r'<section id="doors">.*?</section>')
    for label in ("You sell AI agents", "You build", "You are an agent"):
        assert label in text(doors), label
    hrefs = re.findall(r'<a class="door"[^>]*href="([^"]+)"', doors)
    assert len(hrefs) == 3
    assert any(h.startswith("mailto:sales@actaseal.com") for h in hrefs)
    assert "/docs/" in hrefs and "/llms.txt" in hrefs


# I4 -- CTA
def test_cta_is_pip_install_plus_book_a_demo():
    hero = block(r'<section id="what">.*?</section>')
    assert "<code>pip install actaseal-verify</code>" in hero
    assert re.search(r">\s*Book a demo\s*</a>", hero)
    assert hero.index("pip install") < hero.index('id="receipt-excerpt"')


def test_no_free_tier_offer():
    low = text(raw()).lower()
    for phrase in ("free tier", "free trial", "try it free", "sign up free", "freemium"):
        assert phrase not in low


# I5 -- footer split and machine-readable files
def test_footer_is_split_for_humans_and_for_agents():
    foot = block(r"<footer.*?</footer>")
    t = text(foot)
    assert "For humans" in t and "For agents" in t
    assert t.index("For humans") < t.index("For agents")
    agents = foot[foot.index("For agents"):]
    assert 'href="/llms.txt"' in agents and 'href="/.well-known/ai-catalog.json"' in agents


def test_llms_txt_and_catalog_exist_and_say_only_public_things():
    llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert llms.startswith("# ActaSeal")
    cat = json.loads((ROOT / ".well-known" / "ai-catalog.json").read_text(encoding="utf-8"))
    assert cat["schema"] == "actaseal-ai-catalog.v1"
    assert cat["name"] == "ActaSeal"
    blob = llms + json.dumps(cat)
    for url in re.findall(r"https?://[^\s\"')>]+", blob):
        assert url.startswith(("https://actaseal.com", "https://verify.actaseal.com", "https://cbom.actaseal.com",
                               "https://pypi.org/project/actaseal-verify", "https://github.com/actaseal/")), url
    low = blob.lower()
    for phrase in ("pricing", "price", "tier", "roadmap", "blockchain", "free tier"):
        assert phrase not in low
    assert "mailto:sales@actaseal.com" in blob or "sales@actaseal.com" in blob


# I6 -- nav organised by task
def test_nav_leads_with_tasks_and_keeps_as1215_and_cbom_reachable():
    for page in NAV_PAGES:
        src = (ROOT / page).read_text(encoding="utf-8")
        nav = re.search(r'<nav class="site-nav">.*?</nav>', src, flags=re.S).group(0)
        labels = [text(a) for a in re.findall(r"<a\b[^>]*>(.*?)</a>", nav, flags=re.S)]
        assert labels[0] == "Verify a receipt", (page, labels)
        assert "Build with it" in labels[:3], (page, labels)
        assert any("AS 1215" in l for l in labels) and "CBOM Check" in labels, (page, labels)
        assert labels.index("CBOM Check") > 1 and not labels[0].startswith("AS 1215")
        assert 'href="/as1215/"' in nav and 'href="https://cbom.actaseal.com"' in nav


# I7 -- two proof lines
def test_two_proof_lines_are_present_once():
    sec = text(block(r'<section id="why-it-holds">.*?</section>'))
    assert "Your proof still verifies if we disappear." in sec
    assert "Records live outside the agent, so a compromised agent cannot rewrite them." in sec
    assert "Apache License 2.0" in sec
    assert 'href="/limits/"' in block(r'<section id="why-it-holds">.*?</section>')


# I8 -- standards section
def test_standards_section_keeps_ietf_zenodo_and_lists_the_x402_implementation():
    proof = block(r'<section id="proof">.*?</section>')
    assert "https://datatracker.ietf.org/doc/draft-xg-payment-dispute-profile/" in proof
    assert "https://doi.org/10.5281/zenodo.23309307" in proof
    assert "Independent implementations" in text(proof)
    assert "https://github.com/actaseal/x402-acceptance-check-cold" in proof
    # what the repo's own README measures: 50/50 at upstream 6e487f0
    entry = text(re.search(r"<li><strong>Independent implementations.*?</li>", proof, flags=re.S).group(0))
    assert "all 50 vectors" in entry and "6e487f0" in entry and "46" not in entry


# I9 -- the drop list
def test_nothing_from_the_drop_list_is_on_the_site():
    banned = ("blockchain", "bitcoin", "opentimestamps", "eip-712", "ethereum", "evidence layer",
              "hbom", "saasbom", "obom", "c2pa", "token incentive", "free tier")
    for p in list(ROOT.rglob("*.html")) + [ROOT / "llms.txt", ROOT / ".well-known" / "ai-catalog.json"]:
        if not p.exists() or {"tests", "scripts", ".git"} & set(p.relative_to(ROOT).parts):
            continue
        low = text(p.read_text(encoding="utf-8")).lower()
        for w in banned:
            assert w not in low, f"{p.relative_to(ROOT)} says {w!r}"
