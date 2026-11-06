"""Qualifier Agent: merge Scout + Research data, confirm each company really is a
property manager, add the Berlin district, and compute a transparent 0-100 lead score.

Score (max 100) - why each part matters for a metering provider:
  Portfolio size     35  more units = more meters = more recurring revenue
  Segment fit        20  WEG + rental management both need annual heating-cost billing
  Switch signal      10  mentions metering/heating-cost billing or a competitor (ista, Techem...)
  Digital readiness  15  uses property software / tenant portal -> easier API/portal integration
  Growth             10  currently hiring -> portfolio growing
  Reachability       10  named decision maker + working website
Tier: A >= 60, B 40-59, C < 40
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"


import re as _re
TITLE_RX = _re.compile(r"^(?:(?:Herr|Frau|RA(?:in)?|Rechtsanwalt|Rechtsanwältin|Dipl\.-?[\w\-]*\.?|Dipl\.|Ing\.|Kfm\.|Kffr\.|B\.A\.|M\.A\.|MBA|LL\.M\.)\s+)+")


def clean_name(n):
    if not n:
        return n
    n = TITLE_RX.sub("", n.strip())
    return _re.sub(r"\s+", " ", n).strip()


def point_in_poly(x, y, poly):
    inside = False
    for ring in poly:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
                inside = not inside
            j = i
    return inside


GEO = json.loads((ROOT / "data/geo/bezirke.geojson").read_text())["features"]


def bezirk(loc):
    if not isinstance(loc, dict) or "lng" not in loc:
        return None
    for f in GEO:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            if point_in_poly(loc["lng"], loc["lat"], poly):
                return f["properties"]["name"]
    return None


def size_tier(units, reviews, n_people, legal_form, housing):
    """Return (tier, basis). Stated units win; otherwise a clearly labelled estimate."""
    if units:
        t = "XL (1000+)" if units >= 1000 else "L (300-999)" if units >= 300 else "M (100-299)" if units >= 100 else "S (<100)"
        return t, "stated on website"
    if housing:
        return "XL (1000+)", "estimate: housing company / co-op"
    r = 0 if reviews is None or reviews != reviews else reviews
    # tenants & owners review their Hausverwaltung on Google, so review volume tracks portfolio size
    pts = (2 if r >= 100 else 1.5 if r >= 40 else 1 if r >= 15 else 0.5 if r >= 5 else 0)
    pts += 0.5 if legal_form and "GmbH" in legal_form else 0
    pts += 0.5 if n_people >= 2 else 0
    t = "L (300-999)" if pts >= 2.5 else "M (100-299)" if pts >= 1.5 else "S (<100)"
    return t, f"estimate: {int(r)} Google reviews" + (", GmbH" if legal_form and "GmbH" in legal_form else "") + (f", {n_people} managing directors" if n_people >= 2 else "")


MAX = {"size": 35, "segment": 20, "switch": 10, "digital": 15, "growth": 10, "reach": 10}


def score_row(r):
    parts = {}
    size = r["size_tier"]
    stated = r["size_basis"] == "stated on website"
    base = {"XL": 35, "L": 27, "M": 18, "S": 8}[size.split()[0]]
    parts["size"] = base if stated or r["is_housing"] else round(base * 0.8)  # estimates count a bit less
    seg = 0
    if r["svc_weg"]:
        seg += 10
    if r["svc_miet"]:
        seg += 10
    if r["is_housing"]:
        seg = 20
    if not seg and r["pm_confirmed"]:
        seg = 8
    parts["segment"] = seg
    parts["switch"] = 10 if r["competitor"] else 6 if r["mentions_billing"] else 0
    sw = [x for x in str(r["software"] or "").split(", ") if x]
    named = [x for x in sw if x != "Mieterportal/App"]
    parts["digital"] = (10 if named else 0) + (5 if "Mieterportal/App" in sw else 0)
    parts["growth"] = 10 if r["hiring"] else 0
    parts["reach"] = (6 if r["decision_maker_1"] else 0) + (4 if r["website_status"] == "ok" else 0)
    return sum(parts.values()), parts


def main():
    scout = pd.DataFrame(json.loads((P / "scout_candidates.json").read_text()))
    res = {r["placeId"]: r for r in json.loads((P / "research.json").read_text())}
    mr_p = P / "manual_review.json"
    manual = json.loads(mr_p.read_text()) if mr_p.exists() else {}
    rows = []
    for _, c in scout.iterrows():
        r = res.get(c["placeId"], {})
        loc = c.get("location") if isinstance(c.get("location"), dict) else None
        if c["placeId"] in manual and r.get("units_rejected"):  # human decision on rules-vs-LLM disagreement
            m_ = manual[c["placeId"]]
            r["units"] = {**r["units_rejected"], "value": m_["value"], "is_buildings": False, "verified_by": m_["note"]}
        cats = c["categories"] if isinstance(c["categories"], list) else []
        housing = c["decision_reason"].startswith("housing")
        pm_mentions = r.get("pm_mentions") or 0
        core_cat = c["decision"] == "keep"
        # confirmation rule: Google category + website, or website alone with clear wording
        if pm_mentions >= 3 or (core_cat and pm_mentions >= 1) or housing:
            confirmed, how = True, f"website mentions property management {pm_mentions}x" if pm_mentions else "housing company"
        elif core_cat and (r.get("website_status") != "ok" or (r.get("text_chars") or 0) < 1500):
            confirmed, how = True, "Google category (website has little readable text)"
        else:
            confirmed, how = False, f"website shows no property-management service ({pm_mentions} mentions)"
        u = r.get("units") or {}
        units = u.get("value")
        if u.get("is_buildings"):  # "80 Objekte" -> estimate units (Berlin multi-family avg ~ 15 units/building)
            units = None
        people = r.get("decision_makers") or []
        tier, basis = size_tier(units, c.get("reviewsCount"), len(people), r.get("legal_form"), housing)
        if u.get("is_buildings") and u.get("value"):
            est = u["value"] * 15
            tier = "XL (1000+)" if est >= 1000 else "L (300-999)" if est >= 300 else "M (100-299)" if est >= 100 else "S (<100)"
            basis = f"estimate: {u['value']} {u.get('unit_type')} x ~15 units"
        svc = r.get("services") or {}
        met = r.get("metering_mentions") or {}
        competitors = [k for k in met if "generic" not in k]
        row = {
            "placeId": c["placeId"], "is_housing": housing, "company": c["title"], "type": "Housing company / co-op" if housing else "Hausverwaltung",
            "pm_confirmed": confirmed, "confirmation": how,
            "google_category": c["categoryName"], "address": c["address"], "postal_code": c.get("postalCode"),
            "bezirk": bezirk(loc), "lat": (loc or {}).get("lat"), "lng": (loc or {}).get("lng"),
            "website": r.get("website_final") or c.get("website"), "website_status": r.get("website_status"),
            "phone": c.get("phone"), "google_rating": c.get("totalScore"), "google_reviews": c.get("reviewsCount"),
            "google_maps_url": c.get("url"), "source": c.get("source") or "Google Maps",
            "legal_form": r.get("legal_form"), "register": (r.get("register") or {}).get("value"),
            "founded": (r.get("founded") or {}).get("value"),
            "units_stated": units, "buildings_stated": u.get("value") if u.get("is_buildings") else None,
            "units_evidence": u.get("quote"), "units_source": u.get("source"), "units_check": u.get("verified_by"),
            "size_tier": tier, "size_basis": basis,
            "employees_stated": (r.get("employees") or {}).get("value"),
            "svc_weg": "WEG-Verwaltung" in svc, "svc_miet": "Mietverwaltung" in svc, "svc_se": "SE-Verwaltung" in svc,
            "svc_gewerbe": "Gewerbeverwaltung" in svc,
            "competitor": ", ".join(competitors), "competitor_evidence": "; ".join(met[k]["quote"] for k in competitors)[:400],
            "mentions_billing": "Ableseservice (generic)" in met,
            "software": ", ".join(k for k in (r.get("software") or {}) if k != "DOMUS" or "domus" not in (c["title"] or "").lower()),
            "digital_signals": r.get("digital_signals"), "associations": ", ".join(r.get("associations") or {}),
            "hiring": bool(r.get("hiring")), "hiring_evidence": (r.get("hiring") or {}).get("quote"), "hiring_source": (r.get("hiring") or {}).get("source"),
            "decision_maker_1": clean_name(people[0]["name"]) if people else None, "role_1": people[0]["role"] if people else None,
            "decision_maker_2": clean_name(people[1]["name"]) if len(people) > 1 else None, "role_2": people[1]["role"] if len(people) > 1 else None,
            "impressum_url": r.get("impressum_url"),
            "general_email": next(iter(sorted(r.get("emails_impressum") or r.get("emails_site") or [], key=lambda e: (not e.startswith(("info", "kontakt")), e))), None),
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    # same company behind several Google entries / brands: same register no., or same director + same unit count
    df["_grp"] = df["register"].where(df["register"].notna() & (df["register"] != ""),
                                      df["decision_maker_1"].fillna("") + "|" + df["units_stated"].fillna(-1).astype(str))
    no_reg = df["register"].isna() | (df["register"] == "")
    df.loc[no_reg & (df["decision_maker_1"].isna() | df["units_stated"].isna()), "_grp"] = df["placeId"]
    df = df.sort_values(["google_reviews"], ascending=False, na_position="last")
    alias = df.groupby("_grp")["company"].apply(lambda x: "; ".join(list(x)[1:]))
    df["also_listed_as"] = df["_grp"].map(alias).replace("", None)
    n0 = len(df)
    df = df.drop_duplicates("_grp").drop(columns="_grp")
    # exact same (specific) company name = same company with two map pins
    nm = df["company"].str.lower().str.strip()
    dup = nm.duplicated() & (nm.str.len() > 18)
    df = df[~dup]
    print(f"merged {n0 - len(df)} duplicate brand entries")
    sc = df.apply(score_row, axis=1)
    df["lead_score"] = [s for s, _ in sc]
    df["score_breakdown"] = [" | ".join(f"{k} {v}" for k, v in p.items()) for _, p in sc]
    for k, mx in MAX.items():  # 0-1 factors so the sheet can recompute the score from editable weights
        df[f"f_{k}"] = [round(p[k] / mx, 3) for _, p in sc]
    df.loc[~df["pm_confirmed"], "lead_score"] = 0
    df["tier"] = pd.cut(df["lead_score"], [-1, 39, 59, 101], labels=["C", "B", "A"]).astype(str)
    df.loc[~df["pm_confirmed"], "tier"] = "excluded"
    df = df.sort_values("lead_score", ascending=False)
    df.to_json(P / "leads.json", orient="records", force_ascii=False, indent=1)
    print(df["tier"].value_counts().to_string())
    print(df[df.pm_confirmed]["size_tier"].value_counts().to_string())
    print(df[df.pm_confirmed]["bezirk"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
