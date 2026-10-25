import asyncio, json, re, sys
from urllib.parse import quote_plus
from playwright.async_api import async_playwright
import whisky_lookup as w

async def main(lines):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(w.CDP)
        page = browser.contexts[0].pages[0]
        generic = {"apex","terroir","single","cask","whisky","the","of","de",
                   "and","a","an","year","years","old","yo","biblical","peated",
                   "fortified","wine","m","h","mh","m&h","sc","edition","release",
                   "finish","stare","butelkowanie","wydanie","vintage"}
        out = []
        for raw in lines:
            qname, qabv, qage, qvint, qdec = w.parse_line(raw)
            toks = re.findall(r"[a-z0-9&]+", qname.lower())
            brand = toks[0] if toks else ""
            rare = [t for t in toks[1:] if t not in generic]
            gc = await w.google_candidates(page, brand, qabv, rare)
            await page.wait_for_timeout(800)
            scored = sorted(((w.score(qname, qabv, qage, qvint, qdec, c), c)
                             for c in gc), key=lambda x: -x[0])
            out.append({"input": raw,
                        "google": [{"score": round(s,1), "id": c["id"],
                                    "name": c["name"], "abv": c["strength"]}
                                   for s, c in scored]})
        return out

if __name__ == "__main__":
    lines = [l.strip() for l in sys.stdin if l.strip()]
    res = asyncio.run(main(lines))
    print(json.dumps(res, indent=1))
