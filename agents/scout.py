"""Scout Agent: download Google Maps results from Apify, then clean, filter and dedupe them.

Usage: python agents/scout.py <apify_dataset_id> [<dataset_id> ...]
Needs APIFY_TOKEN in .env
"""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests
import tldextract

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def download(dataset_id: str) -> list[dict]:
    path = RAW / f"gmaps_{dataset_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    token = os.environ["APIFY_TOKEN"]
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    r = requests.get(url, params={"clean": "true", "format": "json", "token": token}, timeout=120)
    r.raise_for_status()
    items = r.json()
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    return items


# --- relevance rules -------------------------------------------------------
# Google category is the strongest signal. Name keywords rescue companies that
# chose a vague category (e.g. "Immobilienagentur") but clearly do management.
CORE_CATEGORIES = {
    "Hausverwaltungsunternehmen", "Immobilienverwaltung", "Hausverwaltung", "Immobilienverwaltungsservice",
    "Grundstücksverwaltung", "Vermietungsagentur für Anlagen mit Eigentumswohnungen",
    # Gelbe Seiten categories
    "Haus- und Grundstücksverwaltungen", "Hausverwaltungen", "Immobilienverwaltungen", "Grundstücksverwaltungen",
    "Wohnungsverwaltung", "WEG-Verwaltung",
}
HOUSING_CATEGORIES = {  # big landlords: they buy metering directly
    "Wohnungsbaugesellschaft", "Wohnungsgenossenschaft", "Wohnungsbaugenossenschaft",
    "Wohnungsbauunternehmen", "Wohnungsbau",
}
MAYBE_CATEGORIES = {
    "Immobilienagentur", "Immobilienmakler", "Immobilienberater", "Immobilienunternehmen", "Immobilienvermittlung",
    "Immobiliengesellschaft", "Vermietungsagentur", "Wohnungsvermietung", "Wohnungsvermietungsagentur",
    "Unternehmensberater", "Wohnanlage", "Agentur für Gewerbeimmobilien", "Immobilieninvestmentgesellschaft",
}
NAME_YES = re.compile(r"hausverw|immobilienverw|grundst(?:ü|ue)cksverw|grundbesitz|verwaltungs(?:gesellschaft|-?gmbh)|verwaltung(?:en)?\b(?!.*(?:haupt))|property\s*manag|immobilienmanagement|\bWEG\b|wohnungsbau|genossenschaft", re.I)
NAME_NO = re.compile(r"software|makler|steuerber|rechtsanw|anwalt|notar|reinigung|hausmeister|bauunternehmen|gutachter|versicherung|winterdienst|umzug", re.I)
NOT_A_CUSTOMER = re.compile(r"hauptverwaltung|stadtreinigung|energie und w(?:ä|ae)rme|verband|e\.\s?V\.|bundesfachverband|unionhilfswerk|kursana", re.I)


def classify(row) -> tuple[str, str]:
    """Return (decision, reason). decision: keep | review | drop"""
    c = row.get("categories")
    cats = set(c if isinstance(c, list) else []) | {_s(row.get("categoryName"))}
    name = _s(row.get("title"))
    if NOT_A_CUSTOMER.search(name):
        return "drop", "headquarters / association / utility, not a property manager"
    mixed = bool(NAME_NO.search(name))
    if cats & HOUSING_CATEGORIES or re.search(r"wohnungsbau|genossenschaft", name, re.I):
        return "keep", "housing company / co-op (large landlord)"
    if cats & CORE_CATEGORIES:
        return ("review", "management category but name suggests broker/other") if mixed else ("keep", "Google category = property management")
    if NAME_YES.search(name):
        return ("review", "name mentions management + other business") if mixed or not (cats & MAYBE_CATEGORIES) else ("keep", "real-estate firm with management in name")
    if mixed:
        return "drop", "name indicates other business"
    if cats & MAYBE_CATEGORIES:
        return "review", "real-estate category, website check needed"
    return "drop", f"unrelated category: {row.get('categoryName')}"


def _s(v):
    return v if isinstance(v, str) else ""


def is_berlin(row) -> bool:
    plz = _s(row.get("postalCode"))
    if not re.fullmatch(r"\d{5}", plz):
        m = re.search(r"\b(1[0-4]\d{3})\b", _s(row.get("address")))
        plz = m.group(1) if m else ""
    return plz.isdigit() and 10115 <= int(plz) <= 14199 and "Berlin" in (_s(row.get("address")) + _s(row.get("city")))


def domain(url):
    if not isinstance(url, str) or not url:
        return None
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}".lower() if ext.domain else None


def main(ids):
    load_env()
    items = []
    for i in ids:
        items += download(i)
    for it in items:
        it["source"] = "Google Maps"
    print(f"raw Google Maps places: {len(items)}")
    gs_p = RAW / "gelbeseiten.json"
    gs = json.loads(gs_p.read_text()) if gs_p.exists() else []
    if gs:
        def key8(p):
            return re.sub(r"\D", "", str(p or ""))[-8:]
        gs_ph = {key8(x.get("phoneUnformatted")) for x in gs if x.get("phoneUnformatted")}
        gs_dom = {domain(x.get("website")) for x in gs if x.get("website")}
        for it in items:
            if (it.get("phoneUnformatted") and key8(it["phoneUnformatted"]) in gs_ph) or (domain(it.get("website")) in gs_dom - {None}):
                it["source"] = "Google Maps + Gelbe Seiten"
        new = [dict(x, source="Gelbe Seiten") for x in gs if not x.get("also_on_google")]
        print(f"Gelbe Seiten: {len(gs)} entries, {len(new)} new")
        items += new
    df = pd.DataFrame(items)
    df = df[df["permanentlyClosed"].fillna(False).astype(bool) == False]
    df = df[df.apply(is_berlin, axis=1)]
    print(f"in Berlin & open: {len(df)}")

    df[["decision", "decision_reason"]] = df.apply(lambda r: pd.Series(classify(r)), axis=1)
    df["domain"] = df["website"].map(domain)
    df["phone_norm"] = df["phoneUnformatted"].fillna("").astype(str).str.replace(r"\D", "", regex=True).str[-8:]

    # dedupe: same Google place, then same website domain, then same phone
    df = df.sort_values("reviewsCount", ascending=False, na_position="last")
    df = df.drop_duplicates("placeId")
    with_dom = df[df["domain"].notna()].drop_duplicates("domain")
    no_dom = df[df["domain"].isna()]
    df = pd.concat([with_dom, no_dom])
    df = pd.concat([df[df["phone_norm"] == ""], df[df["phone_norm"] != ""].drop_duplicates("phone_norm")])
    print(f"after dedupe: {len(df)}")
    print(df["decision"].value_counts().to_string())

    cols = ["placeId", "title", "categoryName", "categories", "address", "street", "postalCode",
            "neighborhood", "location", "website", "domain", "phone", "totalScore", "reviewsCount",
            "url", "searchString", "source", "decision", "decision_reason"]
    df = df[[c for c in cols if c in df.columns]]
    df.to_json(OUT / "scout_all.json", orient="records", force_ascii=False, indent=1)
    df[df["decision"] != "drop"].to_json(OUT / "scout_candidates.json", orient="records", force_ascii=False, indent=1)
    print(f"candidates saved: {(df['decision'] != 'drop').sum()}")


if __name__ == "__main__":
    main(sys.argv[1:])
