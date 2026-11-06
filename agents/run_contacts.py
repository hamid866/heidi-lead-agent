"""Run the Contact agent for A and B leads.
1) emails (published / colleague pattern / common pattern) + MX check  - free
2) LinkedIn: one Google search per decision maker via Apify, best leads first (budget-capped)
Output: data/processed/contacts.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contacts import enrich, google_batch, linkedin_query, match_linkedin  # noqa: E402
from scout import load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"
MAX_QUERIES = 160


def main():
    load_env()
    leads = json.loads((P / "leads.json").read_text())
    res = {r["placeId"]: r for r in json.loads((P / "research.json").read_text())}
    ab = [l for l in leads if l["tier"] in ("A", "B")]
    print(f"contacts for {len(ab)} A/B leads")
    out = {}
    for l in ab:
        out[l["placeId"]] = enrich({"title": l["company"], "website": l["website"]}, res.get(l["placeId"], {}), do_linkedin=False)
    # LinkedIn: best-scored first, first decision maker always, second only for A leads
    queue = []
    for l in sorted(ab, key=lambda x: -x["lead_score"]):
        for k, c in enumerate(out[l["placeId"]]):
            if k == 0 or l["tier"] == "A":
                queue.append((l, c))
    queue = queue[:MAX_QUERIES]
    results = google_batch([linkedin_query(c["name"], l["company"]) for l, c in queue])
    for l, c in queue:
        c["linkedin"] = match_linkedin(results[linkedin_query(c["name"], l["company"])], c["name"], l["company"], c.get("_domain"))
    for v in out.values():
        for c in v:
            c.pop("_domain", None)
    (P / "contacts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    people = [c for v in out.values() for c in v]
    print(f"people: {len(people)} | searched: {len(queue)} | linkedin matched: {sum(1 for c in people if c.get('linkedin'))} | "
          f"email verified: {sum(1 for c in people if c.get('confidence') == 'verified_on_website')} | "
          f"pattern from site: {sum(1 for c in people if c.get('confidence') == 'pattern_from_site')} | "
          f"common pattern: {sum(1 for c in people if c.get('confidence') == 'common_pattern')}")


if __name__ == "__main__":
    main()
