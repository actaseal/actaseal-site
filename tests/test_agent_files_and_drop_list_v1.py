"""llms.txt and the catalog say only public things; nothing from the drop list is on the site."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def test_llms_txt_and_catalog_exist_and_say_only_public_things():
    llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert llms.startswith("# ActaSeal")
    cat = json.loads((ROOT / ".well-known" / "ai-catalog.json").read_text(encoding="utf-8"))
    assert cat["schema"] == "actaseal-ai-catalog.v1" and cat["name"] == "ActaSeal"
    blob = llms + json.dumps(cat)
    for url in re.findall(r"https?://[^\s\"')>]+", blob):
        assert url.startswith(("https://actaseal.com", "https://verify.actaseal.com", "https://cbom.actaseal.com",
                               "https://pypi.org/project/actaseal-verify", "https://github.com/actaseal/")), url
    low = blob.lower()
    for phrase in ("pricing", "price", "tier", "roadmap", "blockchain", "free tier"):
        assert phrase not in low
    assert "sales@actaseal.com" in blob


def test_nothing_from_the_drop_list_is_on_the_site():
    banned = ("blockchain", "bitcoin", "opentimestamps", "eip-712", "ethereum", "evidence layer",
              "hbom", "saasbom", "obom", "c2pa", "token incentive", "free tier")
    for p in list(ROOT.rglob("*.html")) + [ROOT / "llms.txt", ROOT / ".well-known" / "ai-catalog.json"]:
        if not p.exists() or {"tests", "scripts", ".git"} & set(p.relative_to(ROOT).parts):
            continue
        low = text(p.read_text(encoding="utf-8")).lower()
        for w in banned:
            assert w not in low, f"{p.relative_to(ROOT)} says {w!r}"
