"""Load results of a finished Apify google-search-scraper run into the search cache
(used when a long run outlives the synchronous API call)."""
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from scout import load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw/search_cache.json"

load_env()
ds = sys.argv[1]
items = requests.get(f"https://api.apify.com/v2/datasets/{ds}/items",
                     params={"token": os.environ["APIFY_TOKEN"], "clean": "true", "format": "json"}, timeout=120).json()
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
n = 0
for it in items:
    q = (it.get("searchQuery") or {}).get("term")
    if q:
        cache[f"G::{q}"] = [{"title": o.get("title", ""), "url": o.get("url", ""), "snippet": o.get("description", "")}
                            for o in it.get("organicResults", [])]
        n += 1
CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
print(f"cached {n} search result pages")
