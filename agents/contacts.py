"""Contact Agent: for each decision maker found in the Impressum, find
(1) a LinkedIn profile that matches BOTH the person and the company, and
(2) a personal email with an honest confidence label.

Confidence levels for email:
  verified_on_website  - the exact personal address is published on the company site
  pattern_from_site    - built from a colleague's published address pattern on the same domain
  common_pattern       - firstname.lastname@domain (most common German SME pattern), NOT verified
Domains are checked for working mail servers (MX record).
"""
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import dns.resolver
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "search_cache.json"
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
GENERIC = re.compile(r"^(info|kontakt|contact|office|mail|post|service|verwaltung|hausverwaltung|buchhaltung|rechnung|miete|weg|"
                     r"personal|jobs?|karriere|bewerbung|datenschutz|hello|hallo|team|zentrale|empfang|anfrage|vermietung|technik|"
                     r"support|webmaster|admin|noreply|no-reply|presse|marketing|sales|backoffice|notfall|schaden)\b", re.I)
STOP = {"gmbh", "co", "kg", "ug", "ag", "ohg", "mbh", "und", "hausverwaltung", "hausverwaltungen", "immobilien", "verwaltung",
        "berlin", "grundstücksverwaltung", "immobilienverwaltung", "gesellschaft", "real", "estate", "management", "the", "group", "service"}

_cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def ascii_name(s: str) -> str:
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z\-]", "", s)


def split_name(full: str):
    parts = [p for p in re.sub(r"(Dr\.|Dipl\.-?[\w\-]*\.?|Prof\.|\bRA(?:in)?\b|Ing\.|MBA|LL\.M\.)", "", full).split() if p]
    return parts[0], parts[-1]


def company_tokens(title: str, domain: str | None):
    toks = [t for t in re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", title) if t.lower() not in STOP]
    if domain:
        toks.append(domain.split(".")[0])
    return {t.lower() for t in toks}


def ddg(query: str) -> list[dict]:
    if query in _cache:
        return _cache[query]
    for attempt in range(3):
        try:
            r = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=H, timeout=20)
            if r.status_code == 200 and "result__a" in r.text:
                break
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    else:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    res = []
    for div in soup.select("div.result")[:8]:
        a = div.select_one("a.result__a")
        if not a:
            continue
        href = unquote(a["href"])
        m = re.search(r"https?://[^&]+", href)
        snip = div.select_one(".result__snippet")
        res.append({"title": a.get_text(" ", strip=True), "url": m.group(0) if m else href,
                    "snippet": snip.get_text(" ", strip=True) if snip else ""})
    _cache[query] = res
    CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=1))
    time.sleep(2.5)  # be polite
    return res


def find_linkedin(name: str, company_title: str, domain: str | None):
    first, last = split_name(name)
    toks = company_tokens(company_title, domain)
    for q in (f'"{first} {last}" {company_title.split("|")[0][:60]} linkedin',
              f'"{first} {last}" Hausverwaltung Berlin site:linkedin.com/in'):
        for r in ddg(q):
            if "linkedin.com/in/" not in r["url"]:
                continue
            blob = (r["title"] + " " + r["snippet"]).lower()
            if ascii_name(last) not in ascii_name(blob.replace(" ", "")) and last.lower() not in blob:
                continue
            if any(t in blob for t in toks):
                return {"url": r["url"].split("?")[0], "headline": r["title"].replace(" | LinkedIn", ""),
                        "match": "name + company in LinkedIn result"}
    return None


def mx_ok(domain: str) -> bool:
    try:
        return bool(dns.resolver.resolve(domain, "MX", lifetime=8))
    except Exception:
        return False


def pattern_of(email: str, people_names: list[str]):
    """Detect a personal pattern from a published colleague email."""
    local = email.split("@")[0].lower()
    for n in people_names:
        f, l = (ascii_name(x) for x in split_name(n))
        for pat, val in (("first.last", f"{f}.{l}"), ("f.last", f"{f[0]}.{l}"), ("firstlast", f"{f}{l}"),
                         ("first_last", f"{f}_{l}"), ("first-last", f"{f}-{l}"), ("flast", f"{f[0]}{l}"),
                         ("last", l), ("first", f)):
            if local == val:
                return pat
    if re.fullmatch(r"[a-z]+\.[a-z\-]+", local):
        return "first.last?"
    if re.fullmatch(r"[a-z]\.[a-z\-]+", local):
        return "f.last?"
    return None


def build(pat: str, name: str, domain: str) -> str:
    f, l = (ascii_name(x) for x in split_name(name))
    return {"first.last": f"{f}.{l}", "f.last": f"{f[0]}.{l}", "firstlast": f"{f}{l}", "first_last": f"{f}_{l}",
            "first-last": f"{f}-{l}", "flast": f"{f[0]}{l}", "last": l, "first": f}[pat.rstrip("?")] + "@" + domain


def find_email(name: str, emails: list[str], domain: str, all_people: list[str]):
    f, l = (ascii_name(x) for x in split_name(name))
    personal = [e for e in emails if not GENERIC.match(e.split("@")[0])]
    for e in personal:
        loc = ascii_name(e.split("@")[0].replace(".", "").replace("_", ""))
        if l and l in loc:
            return {"email": e, "confidence": "verified_on_website", "how": "address published on company website"}
    for e in personal:
        pat = pattern_of(e, all_people)
        if pat and e.split("@")[1] == domain:
            return {"email": build(pat, name, domain), "confidence": "pattern_from_site",
                    "how": f"same pattern as published colleague address ({pat.rstrip('?')})"}
    return {"email": f"{f}.{l}@{domain}", "confidence": "common_pattern",
            "how": "most common German SME format, not verified - check before sending"}


def enrich(company: dict, research: dict, do_linkedin=True) -> list[dict]:
    people = research.get("decision_makers") or []
    final = research.get("website_final") or company.get("website") or ""
    m = re.search(r"https?://(?:www\.)?([^/:]+)", final)
    domain = m.group(1).lower() if m else None
    emails = sorted(set((research.get("emails_site") or []) + (research.get("emails_impressum") or [])))
    has_mx = mx_ok(domain) if domain else False
    out = []
    for p in people[:2]:
        nm = re.sub(r"^(?:(?:Herr|Frau|RA(?:in)?|Dipl\.-?[\w\-]*\.?|Ing\.)\s+)+", "", p["name"]).strip()
        c = {"name": nm, "role": p["role"], "source": p["source"]}
        if domain and has_mx:
            c.update(find_email(p["name"], emails, domain, [x["name"] for x in people]))
        else:
            c.update({"email": None, "confidence": "no_mail_server", "how": "domain has no MX record"})
        c["linkedin"] = find_linkedin(p["name"], company["title"], domain) if do_linkedin else None
        c["_domain"] = domain
        out.append(c)
    return out


# ---------------------------------------------------------------- Google (Apify) batch mode
def google_batch(queries: list[str], max_usd: float = 0.75) -> dict[str, list[dict]]:
    """One Google results page per query via Apify google-search-scraper (~0.0045 USD each)."""
    todo = [q for q in queries if f"G::{q}" not in _cache]
    if todo and os.environ.get("NO_NEW_SEARCH"):
        print(f"  skipping {len(todo)} uncached searches (NO_NEW_SEARCH set)")
        todo = []
    if todo:
        token = os.environ["APIFY_TOKEN"]
        r = requests.post("https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items",
                          params={"token": token, "maxTotalChargeUsd": max_usd, "timeout": 600},
                          json={"queries": "\n".join(todo), "resultsPerPage": 10, "maxPagesPerQuery": 1,
                                "countryCode": "de", "languageCode": "de"}, timeout=700)
        r.raise_for_status()
        for item in r.json():
            q = (item.get("searchQuery") or {}).get("term")
            if q:
                _cache[f"G::{q}"] = [{"title": o.get("title", ""), "url": o.get("url", ""), "snippet": o.get("description", "")}
                                     for o in item.get("organicResults", [])]
        for q in todo:
            _cache.setdefault(f"G::{q}", [])
        CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=1))
    return {q: _cache.get(f"G::{q}", []) for q in queries}


def linkedin_query(name: str, company_title: str) -> str:
    first, last = split_name(name)
    comp = re.split(r"[|\-–(]", company_title)[0].strip()[:50]
    return f'"{first} {last}" {comp} linkedin'


def match_linkedin(results: list[dict], name: str, company_title: str, domain: str | None):
    first, last = split_name(name)
    toks = company_tokens(company_title, domain)
    for r in results:
        if "linkedin.com/in/" not in r["url"]:
            continue
        blob = (r["title"] + " " + r["snippet"]).lower()
        if ascii_name(last) not in ascii_name(blob) and last.lower() not in blob:
            continue
        if ascii_name(first)[:4] not in ascii_name(blob):
            continue
        if any(t in blob for t in toks):
            return {"url": r["url"].split("?")[0], "headline": re.sub(r"\s*[|–-]\s*LinkedIn.*$", "", r["title"]),
                    "match": "Google result shows person name + company"}
    return None
