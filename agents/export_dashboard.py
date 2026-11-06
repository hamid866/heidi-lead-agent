"""Export the dashboard datasets (leads, contacts, funnel, KPIs, district outlines, spot check)
to output/dashboard/*.json. Lead IDs match the Excel workbook (HV-0001 = highest score)."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_sheet import email_draft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"
OUT = ROOT / "output/dashboard"


def v(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return x


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_leads = json.loads((P / "leads.json").read_text())
    leads = [l for l in all_leads if l["pm_confirmed"]]
    contacts = json.loads((P / "contacts.json").read_text())
    conf = {"verified_on_website": "Verified", "pattern_from_site": "Pattern from colleague",
            "common_pattern": "Likely, unverified", "no_mail_server": "No mail server"}
    rows, crow = [], []
    for i, l in enumerate(leads, 1):
        lid = f"HV-{i:04d}"
        ps = contacts.get(l["placeId"], [])
        best = next((p for p in ps if p.get("confidence") == "verified_on_website"),
                    ps[0] if ps else ({"name": l.get("decision_maker_1")} if l.get("decision_maker_1") else None))
        units = int(l["units_stated"]) if v(l.get("units_stated")) else None
        rows.append({
            "lead_id": lid, "company": l["company"], "tier": l["tier"], "score": int(l["lead_score"]), "type": l["type"],
            "bezirk": v(l.get("bezirk")) or "Unknown", "address": v(l.get("address")), "size_tier": l["size_tier"].split()[0],
            "units": units, "size_basis": l["size_basis"],
            "weg": bool(l["svc_weg"]), "miet": bool(l["svc_miet"]), "se": bool(l["svc_se"]), "gewerbe": bool(l["svc_gewerbe"]),
            "software": v(l.get("software")) or "", "competitor": v(l.get("competitor")) or "",
            "competitor_quote": v(l.get("competitor_evidence")) or None,
            "hiring": bool(l["hiring"]), "hiring_quote": v(l.get("hiring_evidence")), "hiring_source": v(l.get("hiring_source")),
            "associations": v(l.get("associations")) or "", "legal_form": v(l.get("legal_form")), "register": v(l.get("register")),
            "founded": int(l["founded"]) if v(l.get("founded")) else None,
            "employees": int(l["employees_stated"]) if v(l.get("employees_stated")) else None,
            "rating": v(l.get("google_rating")), "reviews": int(l["google_reviews"]) if v(l.get("google_reviews")) else None,
            "website": v(l.get("website")), "website_status": v(l.get("website_status")), "phone": v(l.get("phone")),
            "general_email": v(l.get("general_email")), "listing_url": v(l.get("google_maps_url")),
            "decision_maker": v(l.get("decision_maker_1")), "role": v(l.get("role_1")),
            "decision_maker_2": v(l.get("decision_maker_2")), "role_2": v(l.get("role_2")),
            "found_in": l.get("source") or "Google Maps", "also_listed_as": v(l.get("also_listed_as")),
            "confirmed_because": l["confirmation"],
            "lat": round(l["lat"], 5) if v(l.get("lat")) else None, "lng": round(l["lng"], 5) if v(l.get("lng")) else None,
            "units_quote": v(l.get("units_evidence")) if units else None, "units_source": v(l.get("units_source")) if units else None,
            "units_check": v(l.get("units_check")) if units else None, "impressum": v(l.get("impressum_url")),
            "pts_size": round(l["f_size"] * 35), "pts_segment": round(l["f_segment"] * 20), "pts_switch": round(l["f_switch"] * 10),
            "pts_digital": round(l["f_digital"] * 15), "pts_growth": round(l["f_growth"] * 10), "pts_reach": round(l["f_reach"] * 10),
            "email_draft": email_draft(l, best) if l["tier"] in ("A", "B") else None,
        })
        for k, c in enumerate(ps):
            crow.append({"contact_id": f"{lid}-{k + 1}", "lead_id": lid, "company": l["company"], "tier": l["tier"],
                         "name": c["name"], "role": c["role"], "email": c.get("email"),
                         "email_confidence": conf.get(c.get("confidence"), c.get("confidence")),
                         "linkedin": (c.get("linkedin") or {}).get("url"), "linkedin_headline": (c.get("linkedin") or {}).get("headline")})
    scout = json.loads((P / "scout_all.json").read_text())
    gs = ROOT / "data/raw/gelbeseiten.json"
    raw = 1040 + (len(json.loads(gs.read_text())) if gs.exists() else 0)
    funnel = [{"stage": "Listings found (Google Maps + Gelbe Seiten)", "order": 1, "companies": raw},
              {"stage": "Unique and in Berlin", "order": 2, "companies": len(scout)},
              {"stage": "Researched (websites + Impressum)", "order": 3, "companies": len(all_leads)},
              {"stage": "Confirmed property managers", "order": 4, "companies": len(leads)},
              {"stage": "Tier A + B leads", "order": 5, "companies": sum(1 for l in leads if l["tier"] in "AB")}]
    kpis = [{"kpi": "Portfolio size", "weight": 35, "why": "More units means more meters and more recurring revenue."},
            {"kpi": "Segment fit", "weight": 20, "why": "WEG and rental management need an annual heating-cost bill."},
            {"kpi": "Digital readiness", "weight": 15, "why": "Software or a tenant portal means faster adoption of a digital platform."},
            {"kpi": "Switch signal", "weight": 10, "why": "Mentions heating-cost billing or a competitor such as ista or Techem."},
            {"kpi": "Growth", "weight": 10, "why": "Live job ads (m/w/d) mean a growing portfolio."},
            {"kpi": "Reachability", "weight": 10, "why": "Named managing director and a live website."}]
    geo = json.loads((ROOT / "data/geo/bezirke.geojson").read_text())
    feats = []
    for f in geo["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        out = []
        for poly in polys:
            ring = poly[0]
            r = [[round(x, 4), round(y, 4)] for x, y in ring[::max(1, len(ring) // 160)]]
            if r[0] != r[-1]:
                r.append(r[0])
            if len(r) > 8:
                out.append(r)
        feats.append({"bezirk": f["properties"]["name"], "rings": json.dumps(out)})
    sc = json.loads((P / "spot_check.json").read_text())
    quality = [{"check": "Company is really a property manager", "correct": sc["pm_correct"], "checked": sc["n"], "how": "Random leads checked against their live websites"},
               {"check": "Managing director name", "correct": sc["dm_correct"], "checked": sc["dm_checked"], "how": "Names compared with the Impressum page"},
               {"check": "Units managed figure", "correct": sc["units_correct"], "checked": sc["units_checked"], "how": "Random unit counts compared with the quoted sentence"}]
    for name, data in (("leads", rows), ("contacts", crow), ("funnel", funnel), ("kpis", kpis), ("districts_geo", feats), ("quality", quality)):
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False))
    print(f"dashboard data: {len(rows)} leads, {len(crow)} contacts")


if __name__ == "__main__":
    main()
