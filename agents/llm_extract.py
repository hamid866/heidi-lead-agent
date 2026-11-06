"""LLM agent (free, local via Ollama, qwen2.5:7b). Two jobs, both only where rules are not enough:

1. Decision makers: when the rules found an Impressum but no name, the LLM reads it.
   Guard: a name is only accepted if it appears word for word in the page text.
2. Unit verifier: for every unit count the rules extracted, the LLM checks the quote:
   "Does this sentence state how many units THIS company currently manages?"
   The number is kept only if the LLM agrees AND returns the same number.

All answers are cached in data/processed/llm_cache.json, so reruns are free and instant.
Usage: python agents/llm_extract.py
"""
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from research import fetch, text_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen2.5:7b"
CACHE_P = ROOT / "data/processed/llm_cache.json"
CACHE = json.loads(CACHE_P.read_text()) if CACHE_P.exists() else {}

PEOPLE_PROMPT = """You read the legal notice (Impressum) of a German property management company.
Return JSON: {{"people": [{{"name": "...", "role": "..."}}]}}
List ONLY natural persons who lead or own the company (Geschäftsführer, Inhaber, Vorstand, vertreten durch,
persönlich haftender Gesellschafter). Copy names exactly as written. Do NOT include data-protection officers,
web designers, photographers, supervisory authorities, or company names. If none, return {{"people": []}}.

IMPRESSUM TEXT:
{text}"""

UNITS_PROMPT = """Company: {company}
Sentence from the company's own website: "{quote}"

Question: Does this sentence state how many apartments/units/buildings THIS company CURRENTLY manages
(its own management portfolio)? Answer "no" if the number is a minimum offer ("ab 50 Einheiten"), a client's
or investor's portfolio, a single property for sale, a construction project, a past/future/target value,
a renovation count, or belongs to another city's branch only.
Return JSON: {{"is_current_portfolio": true/false, "number": <integer or null>, "reason": "<short>"}}"""


def llm(prompt: str) -> dict:
    if prompt in CACHE:
        return CACHE[prompt]
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": MODEL, "prompt": prompt, "format": "json", "stream": False,
        "options": {"temperature": 0}}, timeout=180)
    try:
        out = json.loads(r.json()["response"])
    except Exception:
        out = {}
    CACHE[prompt] = out
    CACHE_P.write_text(json.dumps(CACHE, ensure_ascii=False))
    return out


def people_from_impressum(url: str) -> tuple[list[dict], int]:
    _, html = fetch(url)
    t = text_of(html or "")
    m = re.search(r"angaben gem|§\s*5|vertreten|geschäftsf|inhaber|impressum", t, re.I)
    t = t[max(0, m.start() - 300):] if m else t
    people, rejected = [], 0
    for p in llm(PEOPLE_PROMPT.format(text=t[:1600])).get("people", []):
        name = re.sub(r"\s+", " ", str(p.get("name", ""))).strip()
        words = name.split()
        if len(words) < 2 or re.search(r"GmbH|UG|AG\b|KG|e\.V|Verwaltung|Immobilien", name):
            continue
        q = re.search(r"\s+".join(map(re.escape, words)), t)
        if q:
            people.append({"name": name, "role": p.get("role") or "Inhaber/Geschäftsführung", "source": url,
                           "quote": t[max(0, q.start() - 50): q.end() + 30].replace("\n", " "),
                           "method": f"LLM ({MODEL}), verified verbatim in page"})
        else:
            rejected += 1
    return people[:3], rejected


def main():
    path = ROOT / "data/processed/research.json"
    R = json.loads(path.read_text())
    C = {c["placeId"]: c["title"] for c in json.loads((ROOT / "data/processed/scout_candidates.json").read_text())}

    kept = dropped = 0
    for r in R:
        u = r.get("units")
        if not u:
            continue
        ans = llm(UNITS_PROMPT.format(company=C.get(r["placeId"], ""), quote=u["quote"]))
        num = ans.get("number")
        try:
            num = int(str(num).replace(".", "").replace(",", "")) if num is not None else None
        except ValueError:
            num = None
        if ans.get("is_current_portfolio") and num == u["value"]:
            u["verified_by"] = f"rules + LLM ({MODEL})"
            kept += 1
        else:
            r["units_rejected"] = {**u, "llm_reason": ans.get("reason")}
            r["units"] = None
            dropped += 1
    print(f"[units] LLM verifier kept {kept}, rejected {dropped}")
    path.write_text(json.dumps(R, ensure_ascii=False, indent=1))
    todo = [r for r in R if r.get("impressum_url") and not r.get("decision_makers") and (r.get("pm_mentions") or 0) >= 1]
    print(f"[people] Impressum pages without a name: {len(todo)}")
    found = rejected = 0
    for i, r in enumerate(todo, 1):
        people, rej = people_from_impressum(r["impressum_url"])
        rejected += rej
        if people:
            r["decision_makers"] = people
            found += 1
        if i % 25 == 0:
            path.write_text(json.dumps(R, ensure_ascii=False, indent=1))
            print(f"  {i}/{len(todo)} found={found}")
    print(f"[people] LLM added names for {found} companies; rejected {rejected} names not found verbatim")

    path.write_text(json.dumps(R, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
