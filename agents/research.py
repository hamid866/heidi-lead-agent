"""Research Agent: crawl each company's website (home, Impressum, about, services, jobs)
and extract qualifying facts with rules first. Every fact keeps its evidence
(source URL + exact quote) so it can be verified later.

Usage: python agents/research.py [--limit N]
Input:  data/processed/scout_candidates.json
Output: data/processed/research.json, page cache in data/raw/pages/
"""
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "pages"
CACHE.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
           "Accept-Language": "de-DE,de;q=0.9"}

LINK_TYPES = {
    "impressum": re.compile(r"impressum|imprint|legal[-_ ]?notice|anbieterkennzeichnung", re.I),
    "about": re.compile(r"über[-_ ]?uns|ueber[-_ ]?uns|about|unternehmen|wir[-_ ]?über|team|philosophie|geschichte", re.I),
    "services": re.compile(r"leistung|service|verwaltung|weg|miet|angebot|portfolio", re.I),
    "jobs": re.compile(r"karriere|\bjobs?\b|stellenangebot|offene[-_ ]stellen|career", re.I),
    "contact": re.compile(r"kontakt|contact|ansprechpartner", re.I),
}


def fetch(url: str) -> tuple[str | None, str | None]:
    """Return (final_url, html) with on-disk cache."""
    key = CACHE / (hashlib.md5(url.encode()).hexdigest() + ".json")
    if key.exists():
        d = json.loads(key.read_text())
        return d["url"], d["html"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        ok = r.status_code < 400 and "html" in r.headers.get("content-type", "")
        html = r.text if ok else None
        final = r.url
    except requests.RequestException:
        final, html = None, None
    key.write_text(json.dumps({"url": final, "html": html}))
    return final, html


def text_of(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    meta = []  # keep title/description: JavaScript sites often have nothing else
    if soup.title and soup.title.string:
        meta.append(soup.title.string)
    for m in soup.find_all("meta", attrs={"name": re.compile("description|author", re.I)}):
        if m.get("content"):
            meta.append(m["content"])
    for br in soup.find_all("br"):
        br.replace_with("\n")
    txt = "\n".join(meta) + "\n" + soup.get_text("\n")
    if "Ã" in txt:  # UTF-8 page decoded as Latin-1
        try:
            txt = txt.encode("latin-1", "ignore").decode("utf-8", "ignore")
        except Exception:
            pass
    txt = txt.replace("\xad", "").replace("\u200b", "")
    txt = re.sub(r"[ \t\xa0]+", " ", txt)
    return re.sub(r"\n\s*\n+", "\n", txt).strip()


def find_links(base: str, html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(base).netloc.replace("www.", "")
    found = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        if urlparse(href).netloc.replace("www.", "") != host:
            continue
        label = f"{a.get_text(' ', strip=True)} {urlparse(href).path}"
        for kind, rx in LINK_TYPES.items():
            if kind not in found and rx.search(label):
                found[kind] = href.split("#")[0]
    return found


def quote(text: str, m: re.Match, pad: int = 70) -> str:
    s, e = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return re.sub(r"\s+", " ", text[s:e]).strip()


# ---------------------------------------------------------------- extractors
NUM = r"(\d{1,3}(?:[.\s]\d{3})+|\d{2,6})"
UNITS_RX = re.compile(
    rf"(?:über|ca\.?|rund|mehr als|insgesamt|aktuell|knapp|etwa)?\s*{NUM}\s*\+?\s*"
    r"((?:Wohn-?\s*und\s*Gewerbe|Miet-?\s*und\s*Eigentums)?[\w\-]*(?:einheiten|wohnungen)|WE\b|Objekte|Liegenschaften|Häuser)", re.I)
NOT_PORTFOLIO = re.compile(r"\bab\s*$|bis\s*zu\s*$|mindestens|nicht mehr als|nur ab|größe von|\d\s*[-–]\s*$|kaufpreis|€|investor|sucht|"
                           r"entsteh|saniert|verkauf|vermarkt|neubau|soll\b|plant|bis\s*20[3-9]\d|hamburg|münchen|frankfurt|köln", re.I)
EMPLOYEES_RX = re.compile(rf"{NUM}\s*(?:engagierte\s*|qualifizierte\s*|erfahrene\s*)?(Mitarbeiter(?:innen)?|Mitarbeitende|Angestellte|Kolleg)", re.I)
FOUNDED_RX = re.compile(r"(?:gegründet|gründungsjahr|gründung|founded)\D{0,25}?((?:18[5-9]|19\d|20[0-2])\d)|seit\s*(?:dem\s*jahr\s*)?((?:18[5-9]|19\d|20[01])\d)\s*(?:sind|ist|verwalt|betreu|als|steht|erfolgreich|im\s|in\s|für|kümmer|bieten)", re.I)
GF_RX = re.compile(
    r"(Geschäftsführ(?:er|erin|ung|ende\s*Gesellschafter(?:in)?)|Vertretungsberechtigte?r?\s*(?:Geschäftsführer)?|Vertreten\s*durch(?:\s*(?:den|die)\s*Geschäftsführer(?:in)?)?|Inhaber(?:in)?|Vorsitzende[rn]?\s*des\s*Vorstand(?:e?s)?|Vorstand|Verantwortlich(?:er)?\s*(?:i\.\s*S\.\s*d\.)?|Managing\s*Directors?)"
    r"[ \t]*(?:\([^)]*\))?\s*[:\-–]?\s*((?:(?:Dr\.|Dipl\.-?[\w\-]*\.?|Prof\.)[ ]*)*[A-ZÄÖÜ][a-zäöüßéè]+(?:-[A-ZÄÖÜ][a-zäöüßéè]+)?(?:[ ]+(?:von[ ]+|van[ ]+|de[ ]+|zu[ ]+)?[A-ZÄÖÜ][a-zäöüßéè]+(?:-[A-ZÄÖÜ][a-zäöüßéè]+)?){1,2}"
    r"(?:[ ]*(?:,|und|&|sowie)[ ]*(?:(?:Dr\.|Dipl\.-?[\w\-]*\.?)[ ]*)*[A-ZÄÖÜ][a-zäöüßéè]+(?:-[A-ZÄÖÜ][a-zäöüßéè]+)?(?:[ ]+(?:von[ ]+)?[A-ZÄÖÜ][a-zäöüßéè]+(?:-[A-ZÄÖÜ][a-zäöüßéè]+)?){1,2})*)")
NOT_NAME = re.compile(r"GmbH|Straße|Str\.|Berlin|Amtsgericht|Register|Links?\b|Datenschutz|Impressum|Kontakt|Telefon|Tel\b|Fax|Mail|Sitz|Gesellschaft|Verwaltung|Immobilien|Haftung|Inhalt|Angaben|Steuer|Nummer|Aufsicht|Behörde|Recht|Partner|Team|Firma|Unternehmen|Haus|Service", re.I)
HRB_RX = re.compile(r"(HR[AB])\s*(?:Nr\.?|-Nr\.?)?\s*:?\s*(\d{3,6})\s*([A-Z]{1,2})?", re.I)
LEGAL_RX = re.compile(r"\b(GmbH\s*&\s*Co\.\s*KG|GmbH|UG\s*\(haftungsbeschränkt\)|AG|KG|OHG|GbR|e\.\s?K(?:fm)?\.?|eG)\b")
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

SERVICES = {
    "WEG-Verwaltung": r"WEG[-\s]?Verwaltung|Wohnungseigentümergemeinschaft|WEG\b|Eigentümergemeinschaft",
    "Mietverwaltung": r"Mietverwaltung|Mietshausverwaltung|Miethausverwaltung|Zinshaus",
    "SE-Verwaltung": r"Sondereigentumsverwaltung|SE[-\s]Verwaltung|Sondereigentum",
    "Gewerbeverwaltung": r"Gewerbeverwaltung|Gewerbeimmobilien|Gewerbeobjekte",
}
METERING = {  # competitors / current metering partners
    "ista": r"\bista\b", "Techem": r"\btechem\b", "Brunata-Metrona": r"brunata|metrona",
    "Minol": r"\bminol\b", "KALO": r"\bkalo\b", "Noventic/QUNDIS": r"noventic|qundis",
    "Ableseservice (generic)": r"Heizkostenabrechnung|Ablesedienst|Messdienst",
}
SOFTWARE = {
    "casavi": r"casavi", "Facilioo": r"facilioo", "Immoware24": r"immoware", "DOMUS": r"\bdomus\b",
    "Haufe/PowerHaus": r"powerhaus|haufe", "Karthago": r"karthago", "Wodis": r"wodis", "Aareon": r"aareon",
    "ImmoMio": r"immomio", "Objego": r"objego", "Mieterportal/App": r"mieterportal|eigentümerportal|kundenportal|mieter-app|eigentümer-app|online[-\s]portal",
}
ASSOCIATIONS = {"VDIV": r"VDIV|Verband der Immobilienverwalter", "BVI": r"\bBVI\b|Bundesfachverband der Immobilienverwalter",
                "IVD": r"\bIVD\b|Immobilienverband Deutschland", "Haus & Grund": r"Haus\s*&\s*Grund", "BBU": r"\bBBU\b"}
DIGITAL_WORDS = r"digital|online|app\b|portal|smart|papierlos|24/7"


def best_units(texts):
    best = None
    for src, t in texts:
        for m in UNITS_RX.finditer(t):
            n = int(re.sub(r"\D", "", m.group(1)))
            unit = m.group(2).lower()
            near = t[max(0, m.start() - 45): m.start()] + " " + t[m.end(): m.end() + 45]
            if NOT_PORTFOLIO.search(t[max(0, m.start() - 45): m.start()]) or re.search(r"entsteh|saniert|verkauft|vermarktung|kaufpreis|€", near, re.I):
                continue
            # ignore years, phone fragments and tiny numbers
            if n < 20 or 1950 <= n <= 2030 or n > 200000:
                continue
            before = t[max(0, m.start() - 90): m.start() + 25].lower()
            after = t[m.end(): m.end() + 60].lower()
            verb = r"verwalt|betreu|bewirtschaft|portfolio|bestand|manag|anvertraut|insgesamt|über|mehr als|rund|ca\."
            if not (re.search(verb, before) or re.search(r"^\W{0,3}(?:in\s|im\s)?\S*\s?(?:verwalt|betreu|bewirtschaft|unter verwaltung|anvertraut)", after)):
                continue
            if "\n" in t[m.start(): m.end()]:
                continue
            score = 2 if ("einheit" in unit or "wohnung" in unit or unit == "we") else 1
            if not best or (score, n) > (best["score"], best["value"]):
                best = {"value": n, "unit_type": m.group(2), "score": score, "source": src, "quote": quote(t, m),
                        "is_buildings": score == 1}
    return best


def find_first(rx, texts, flags=re.I):
    for src, t in texts:
        m = re.search(rx, t, flags)
        if m:
            return {"source": src, "quote": quote(t, m)}
    return None


def research(company: dict) -> dict:
    out = {"placeId": company["placeId"], "website_status": "no website"}
    site = company.get("website")
    if not site:
        return out
    site = re.sub(r"\?utm_[^#]*", "", site)
    final, html = fetch(site)
    if not html:
        p = urlparse(site if "://" in site else "http://" + site)
        hostn = p.netloc.removeprefix("www.")
        for alt in (f"https://www.{hostn}", f"https://{hostn}", f"http://www.{hostn}", f"http://{hostn}"):
            final, html = fetch(alt)
            if html:
                break
    if not html:
        out["website_status"] = "unreachable"
        return out
    out["website_status"] = "ok"
    out["website_final"] = final
    pages = {"home": (final, html)}
    links = find_links(final, html)
    if "impressum" not in links:
        for path in ("/impressum", "/impressum/", "/impressum.html", "/impressum.php", "/de/impressum"):
            u, h = fetch(urljoin(final, path))
            if h and re.search(r"impressum|angaben gemäß|§\s*5", h, re.I):
                pages["impressum"] = (u, h)
                break
    for kind in ("impressum", "about", "services", "jobs", "contact"):
        if kind in pages:
            continue
        if kind in links:
            u, h = fetch(links[kind])
            if h:
                pages[kind] = (u, h)
        time.sleep(0.2)
    texts = [(u, text_of(h)) for _, (u, h) in pages.items()]
    out["pages_read"] = [u for u, _ in texts]
    all_text = "\n".join(t for _, t in texts)

    # --- Impressum facts (legal data, highest trust)
    imp = next(((u, text_of(h)) for k, (u, h) in pages.items() if k == "impressum"), None)
    if not imp:  # Impressum is sometimes on the home/contact page
        imp = next(((u, t) for u, t in texts if re.search(r"impressum|angaben gemäß", t, re.I)), None)
    if imp:
        u, t = imp
        out["impressum_url"] = u
        people = []
        for m in GF_RX.finditer(t):
            grp = m.group(2)
            if re.match(r"\s*(?:Str\.|Straße|Strasse|str\.|-Str|Weg\b|Allee|Platz|Damm|Ring\b|Ufer)", t[m.end(2):m.end(2) + 12]):
                grp = grp.rsplit(" ", 1)[0]  # last word was the start of a street name
            for n in re.split(r"\s*(?:,|\bund\b|&|\bsowie\b)\s*", grp):
                n = n.strip()
                if 2 <= len(n.split()) <= 5 and n not in [p["name"] for p in people] and not NOT_NAME.search(n):
                    people.append({"name": n, "role": m.group(1).strip(), "source": u, "quote": quote(t, m, 40)})
        seen, uniq = set(), []
        for p_ in people:
            if p_["name"].lower() not in seen:
                seen.add(p_["name"].lower()); uniq.append(p_)
        out["decision_makers"] = uniq[:3]
        hrb = HRB_RX.search(t)
        if hrb:
            court = re.search(r"Amtsgericht\s+([A-ZÄÖÜ][\w\-]+(?:\s*\([^)]*\))?)", t)
            out["register"] = {"value": f"{hrb.group(1).upper()} {hrb.group(2)} {hrb.group(3) or ''}".strip()
                               + (f", AG {court.group(1)}" if court else ""), "source": u, "quote": quote(t, hrb, 40)}
        lf = LEGAL_RX.search(t[:3000])
        if lf:
            out["legal_form"] = re.sub(r"\s+", " ", lf.group(1))
        out["emails_impressum"] = sorted(set(e.lower().rstrip(".") for e in EMAIL_RX.findall(t)))

    host = urlparse(final).netloc.lower().removeprefix("www.")
    base = ".".join(host.split(".")[-2:])
    def own(e):
        d = e.split("@")[1]
        return d == base or d.endswith("." + base) or base.split(".")[0] in d
    out["emails_site"] = sorted(set(e.lower().rstrip(".") for e in EMAIL_RX.findall(all_text) if own(e.lower()) and not e.lower().endswith((".png", ".jpg", ".webp"))))
    out["emails_other_domain"] = sorted(set(e.lower() for e in EMAIL_RX.findall(all_text) if not own(e.lower())))[:5]
    out["units"] = best_units(texts)
    m = None
    for src, t in texts:
        m = EMPLOYEES_RX.search(t)
        if m and 2 <= int(re.sub(r"\D", "", m.group(1))) <= 5000:
            out["employees"] = {"value": int(re.sub(r"\D", "", m.group(1))), "source": src, "quote": quote(t, m)}
            break
    for src, t in texts:
        m = FOUNDED_RX.search(t)
        if m:
            out["founded"] = {"value": int(m.group(1) or m.group(2)), "source": src, "quote": quote(t, m)}
            break

    out["services"] = {k: v for k, rx in SERVICES.items() if (v := find_first(rx, texts))}
    out["metering_mentions"] = {k: v for k, rx in METERING.items() if (v := find_first(rx, texts))}
    out["software"] = {k: v for k, rx in SOFTWARE.items() if (v := find_first(rx, texts))}
    out["associations"] = {k: v for k, rx in ASSOCIATIONS.items() if (v := find_first(rx, texts, 0 if k != "Haus & Grund" else re.I))}
    out["hiring"] = None
    if "jobs" in pages:
        jt = text_of(pages["jobs"][1])
        jm = re.search(r"\((?:m|w|d|x)\s*/\s*(?:m|w|d|x)\s*/\s*(?:m|w|d|x)\)|\b(?:m|w)/(?:w|m)/d\b", jt, re.I)
        if jm:
            out["hiring"] = {"source": pages["jobs"][0], "quote": quote(jt, jm)}
    out["digital_signals"] = len(set(w.lower() for w in re.findall(DIGITAL_WORDS, all_text, re.I)))
    out["text_chars"] = len(all_text)
    out["pm_mentions"] = len(re.findall(r"hausverwalt|immobilienverwalt|weg-verwalt|mietverwalt|sondereigentumsverwalt|wohnungseigentümergemeinschaft|objektbetreuung|property management", all_text, re.I))
    return out


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    comps = json.loads((ROOT / "data/processed/scout_candidates.json").read_text())[:limit]
    results = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(research, c): c for c in comps}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                results.append(f.result())
            except Exception as e:  # never lose a company because one page broke
                results.append({"placeId": futs[f]["placeId"], "website_status": f"error: {e}"})
            if i % 50 == 0:
                print(f"  researched {i}/{len(comps)}")
    (ROOT / "data/processed/research.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    ok = [r for r in results if r.get("website_status") == "ok"]
    print(f"done: {len(results)} companies, {len(ok)} websites read")
    for k in ("units", "employees", "founded", "register", "impressum_url"):
        print(f"  {k}: {sum(1 for r in ok if r.get(k))}")
    print(f"  decision makers: {sum(1 for r in ok if r.get('decision_makers'))}")


if __name__ == "__main__":
    main()
