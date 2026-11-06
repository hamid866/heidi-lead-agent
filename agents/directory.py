"""Directory agent: second, free source (Gelbe Seiten) to close coverage gaps of the
Google Maps run (e.g. Spandau, Lichtenberg) and to cross-check companies.
Addresses are geocoded with OpenStreetMap Nominatim (1 request/second, cached).

Output: data/raw/gelbeseiten.json (Google-Maps-like records, so the Scout agent can merge them)
"""
import base64
import difflib
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/gelbeseiten.json"
GEO_CACHE = ROOT / "data/raw/geocode_cache.json"
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
     "Accept-Language": "de-DE", "X-Requested-With": "XMLHttpRequest"}
TERMS = ["hausverwaltungen", "immobilienverwaltung", "weg-verwaltung"]


def parse(html: str) -> list[dict]:
    out = []
    for a in BeautifulSoup(html, "lxml").select("article.mod-Treffer"):
        name = a.select_one("h2")
        addr = a.select_one(".mod-AdresseKompakt__adress-text")
        if not name or not addr:
            continue
        for e in addr.select(".mod-AdresseKompakt__entfernung"):
            e.decompose()
        address = re.sub(r"\s+", " ", addr.get_text(" ", strip=True)).replace(" ,", ",")
        ortsteil = re.search(r"\(([^)]+)\)", address)
        plz = re.search(r"\b(1[0-4]\d{3})\b", address)
        web = a.select_one("[data-webseitelink]")
        site = base64.b64decode(web["data-webseitelink"]).decode("utf-8", "ignore") if web else None
        tel = a.select_one(".mod-TelefonnummerKompakt__phoneNumber")
        rating = a.select_one(".mod-BewertungKompakt__number")
        nrev = a.select_one(".mod-BewertungKompakt__text")
        cat = a.select_one(".mod-Treffer--besteBranche")
        link = a.select_one("a[href*='/gsbiz/']")
        out.append({
            "placeId": "GS-" + a.get("data-teilnehmerid", ""),
            "title": name.get_text(" ", strip=True),
            "categoryName": cat.get_text(" ", strip=True) if cat else None,
            "address": re.sub(r"\s*\([^)]*\)\s*", " ", address).strip(),
            "ortsteil": ortsteil.group(1) if ortsteil else None,
            "postalCode": plz.group(1) if plz else None,
            "city": "Berlin",
            "website": site,
            "phone": tel.get_text(strip=True) if tel else None,
            "phoneUnformatted": re.sub(r"\D", "", tel.get_text()) if tel else None,
            "totalScore": float(rating.get_text(strip=True).replace(",", ".")) if rating else None,
            "reviewsCount": int(re.sub(r"\D", "", nrev.get_text()) or 0) if nrev else None,
            "url": link["href"] if link else None,
            "permanentlyClosed": False,
            "searchString": "gelbeseiten",
        })
    return out


def collect() -> list[dict]:
    s = requests.Session()
    seen, rows = set(), []
    for term in TERMS:
        r = s.get(f"https://www.gelbeseiten.de/suche/{term}/berlin", headers=H, timeout=30)
        batch = parse(r.text)
        pos = 51
        while True:
            for b in batch:
                if b["placeId"] not in seen:
                    seen.add(b["placeId"])
                    rows.append(b)
            time.sleep(1.0)
            j = s.post("https://www.gelbeseiten.de/ajaxsuche", headers=H, timeout=30,
                       data={"umkreis": "-1", "verwandt": "false", "WAS": term, "WO": "berlin", "position": str(pos),
                             "anzahl": "50", "sortierung": "relevanz"}).json()
            if not j.get("anzahlTreffer"):
                break
            batch = parse(j["html"])
            pos += j["anzahlTreffer"]
            if pos > 3000:
                break
        print(f"  {term}: total unique so far {len(rows)}")
    return rows


def geocode(rows):
    cache = json.loads(GEO_CACHE.read_text()) if GEO_CACHE.exists() else {}
    for i, r in enumerate(rows):
        q = r["address"]
        if q not in cache:
            try:
                res = requests.get("https://nominatim.openstreetmap.org/search", timeout=20,
                                   params={"q": q, "format": "json", "limit": 1, "countrycodes": "de"},
                                   headers={"User-Agent": "heidi-lead-agent/1.0 (case study)"}).json()
                cache[q] = {"lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])} if res else None
            except Exception:
                cache[q] = None
            time.sleep(1.05)
            if i % 50 == 0:
                GEO_CACHE.write_text(json.dumps(cache))
        r["location"] = cache[q]
    GEO_CACHE.write_text(json.dumps(cache))


def norm_name(n):
    n = (n or "").lower()
    n = n.replace("mangement", "management").replace(".", "")
    n = re.sub(r"gmbh|&|\bco\b|\bkg\b|mbh|\bug\b|haftungsbeschränkt|\bek\b|inh .*|hausverwaltung(en)?|immobilien(verwaltung)?|verwaltung|\bund\b|\bfür\b", " ", n)
    return " ".join(sorted(re.findall(r"[a-zäöüß]{3,}", n)))


def main():
    import tldextract
    import sys
    rows = json.loads(OUT.read_text()) if ("--rematch" in sys.argv and OUT.exists()) else collect()
    print(f"Gelbe Seiten entries: {len(rows)}")
    g = [x for x in json.loads((ROOT / "data/processed/scout_all.json").read_text())
         if not str(x.get("placeId", "")).startswith("GS-")]  # compare against Google Maps entries only
    phones = {re.sub(r"\D", "", str(x.get("phone") or ""))[-8:] for x in g if x.get("phone")}
    doms = {x["domain"] for x in g if x.get("domain")}
    names = {norm_name(x["title"]) for x in g}
    for r in rows:
        ext = tldextract.extract(r["website"]) if r.get("website") else None
        dom = f"{ext.domain}.{ext.suffix}".lower() if ext and ext.domain else None
        ph = (r.get("phoneUnformatted") or "")[-8:]
        nn = norm_name(r["title"])
        fuzzy = nn and any(difflib.SequenceMatcher(None, nn, x).ratio() >= 0.88 for x in names if x and abs(len(x) - len(nn)) < 8)
        r["also_on_google"] = bool((ph and ph in phones) or (dom and dom in doms) or nn in names or fuzzy)
    new = [r for r in rows if not r["also_on_google"]]
    print(f"already found on Google Maps: {len(rows) - len(new)} | new from Gelbe Seiten: {len(new)}")
    geocode(new)
    print(f"geocoded: {sum(1 for r in rows if r.get('location'))}/{len(rows)}")
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
