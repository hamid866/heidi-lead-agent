"""Browser agent: some websites build their content with JavaScript or block simple
HTTP clients. This renders them in a real headless Chrome (Playwright) and stores the
result in the same page cache the Research agent reads.

Targets: websites that were unreachable or returned almost no text.
"""
import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw/pages"
LINK = re.compile(r"impressum|imprint|über[-_ ]?uns|ueber[-_ ]?uns|about|leistung|karriere|jobs|kontakt|team", re.I)


def key(url):
    return CACHE / (hashlib.md5(url.encode()).hexdigest() + ".json")


async def render(ctx, url):
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        html = await page.content()
        ok = resp is not None and resp.status < 400
        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => [e.href, e.innerText])")
        return (page.url, html if ok else None, links)
    except Exception:
        return (None, None, [])
    finally:
        await page.close()


async def handle(ctx, sem, url):
    async with sem:
        final, html, links = await render(ctx, url)
        if not html:
            return url, False
        key(url).write_text(json.dumps({"url": final, "html": html}))
        host = urlparse(final).netloc
        seen = set()
        for href, label in links:
            href = href.split("#")[0]
            if urlparse(href).netloc != host or href in seen or not LINK.search(f"{label} {href}"):
                continue
            seen.add(href)
            if len(seen) > 6:
                break
            f2, h2, _ = await render(ctx, href)
            if h2:
                key(href).write_text(json.dumps({"url": f2, "html": h2}))
        return url, True


async def main():
    R = json.loads((ROOT / "data/processed/research.json").read_text())
    C = {c["placeId"]: c for c in json.loads((ROOT / "data/processed/scout_candidates.json").read_text())}
    targets = [re.sub(r"\?utm_[^#]*", "", C[r["placeId"]]["website"]) for r in R
               if C[r["placeId"]].get("website") and (r.get("website_status") == "unreachable" or (r.get("text_chars") or 0) < 800)]
    print(f"rendering {len(targets)} sites with headless Chrome")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(locale="de-DE", user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36")
        sem = asyncio.Semaphore(6)
        res = await asyncio.gather(*(handle(ctx, sem, u) for u in targets))
        await b.close()
    print(f"rendered OK: {sum(ok for _, ok in res)} / {len(targets)}")


if __name__ == "__main__":
    asyncio.run(main())
