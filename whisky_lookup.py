#!/usr/bin/env python3
"""Whiskybase lookup: given free-text whisky lines, find the matching bottle,
its rating, ABV and lowest listed shop price (EUR), plus a match-confidence
score. Drives the session's real Chrome over CDP (Cloudflare blocks plain HTTP).

Usage:  python3 whisky_lookup.py < whiskies.txt
Input lines: free text incl. ABV like "54,2%" or "58.7%". Decade hints like
"lata 80" (1980s) / "(stare butelkowanie lata 70.)" are understood.
"""

import asyncio, csv, json, re, sys
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

CDP = "http://localhost:29229"
SEARCH = "https://www.whiskybase.com/search?q={q}"
BOTTLE = "https://www.whiskybase.com/whiskies/whisky/{id}"
DELAY = 1200  # ms between page loads

# hardcoded FX approximations -> EUR
FX = {"€": 1.0, "£": 1.17, "$": 0.92}


def parse_line(line):
    m = re.search(r"(\d+[.,]\d+)\s*%", line)
    abv = float(m.group(1).replace(",", ".")) if m else None
    # decade hints: "lata 80", "lata 90.", "(lata 70.)", "80s"
    dec = None
    m = re.search(r"lata\s*(\d)\d", line, re.I) or re.search(r"\b(\d)0s\b", line)
    if m:
        dec = 1900 + int(m.group(1)) * 10
    name = re.sub(r"\d+[.,]\d+\s*%", "", line)
    name = re.sub(r"\([^)]*\)|lata\s*\d+\.?", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name, abv, dec


def tokens(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def score(qname, qabv, qdec, cand):
    """cand: {name, strength, bottled}. ABV mismatch is near-fatal."""
    q, r = tokens(qname), tokens(cand["name"])
    overlap = len(q & r) / max(len(q), 1)
    s = 55 * overlap
    if qabv is not None and cand["strength"] is not None:
        if abs(qabv - cand["strength"]) <= 0.11:
            s += 45
        else:
            s -= 60  # almost certainly the wrong bottle
    if qdec is not None and cand["bottled"]:
        if qdec <= cand["bottled"] <= qdec + 9:
            s += 15
        else:
            s -= 15
    return s


async def search_candidates(page, query):
    await page.goto(SEARCH.format(q=query), wait_until="load")
    await page.wait_for_timeout(4500)
    rows = await page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('tr').forEach(tr => {
            const a = tr.querySelector('a[href*="/whiskies/whisky/"]');
            if (!a) return;
            const id = a.href.match(/whiskies\\/whisky\\/(\\d+)/)[1];
            const t = tr.innerText;
            const str = t.match(/(\\d+[.,]\\d+)\\s*%/);
            // bottled year: a 19xx/20xx in the row, prefer the one near "Bottled" col;
            // simplest: take all years, pick any plausible bottled year
            const years = [...t.matchAll(/\\b(19|20)\\d{2}\\b/g)].map(x => +x[0]);
            out.push({id, name: a.innerText.trim(),
                      strength: str ? parseFloat(str[1].replace(',', '.')) : null,
                      bottled: years.length ? Math.max(...years) : null});
        });
        return out;
    }""")
    seen, cands = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            cands.append(r)
    return cands[:10]


async def bottle_details(page, wb_id):
    await page.goto(BOTTLE.format(id=wb_id), wait_until="load")
    await page.wait_for_timeout(3000)
    text = await page.inner_text("body")
    d = {"name": None, "rating": None, "votes": None, "abv": None,
         "shops": None, "lowest_price_eur": None}
    m = re.search(r"([\d.]+)\s*/\s*100", text)
    if m:
        d["rating"] = float(m.group(1))
    m = re.search(r"(?:ratings|Ratings)\s*\n\s*(\d+)", text) or \
        re.search(r"(\d+)\s+ratings", text, re.I)
    if m:
        d["votes"] = int(m.group(1))
    m = re.search(r"Strength\s*\n\s*([\d.]+)\s*%", text)
    if m:
        d["abv"] = float(m.group(1))
    m = re.search(r"Found (\d+) online shops?\.\s*Lowest price:\s*\n?\s*([€£$])\s*([\d.,]+)", text)
    if m:
        d["shops"] = int(m.group(1))
        price = float(m.group(3).replace(",", ""))
        d["lowest_price_eur"] = round(price * FX.get(m.group(2), 1.0), 2)
    try:
        d["name"] = (await page.inner_text("h1")).strip().replace("\n", " ")
    except Exception:
        pass
    return d


async def main(lines):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        results = []
        generic = {"apex", "terroir", "single", "cask", "whisky", "the",
                   "of", "de", "and", "a", "an", "year", "years", "old",
                   "biblical", "peated", "fortified", "wine", "m", "h",
                   "mh", "m&h", "sc", "yo", "edition", "release"}
        for raw in lines:
            qname, qabv, qdec = parse_line(raw)
            cands = await search_candidates(page, quote_plus(qname))
            await page.wait_for_timeout(DELAY)
            def best(cs):
                scored = sorted(
                    ((score(qname, qabv, qdec, c), c) for c in cs),
                    key=lambda x: -x[0])
                return scored[0][0] if scored else -999
            if len(cands) < 3 or best(cands) < 55:
                toks = re.findall(r"[a-z0-9&]+", qname.lower())
                brand = toks[0] if toks else ""
                rare = [t for t in toks[1:] if t not in generic]
                q2 = (brand + " " + " ".join(rare)).strip()
                if q2.lower() != qname.lower():
                    more = await search_candidates(page, quote_plus(q2))
                    await page.wait_for_timeout(DELAY)
                    ids = {c["id"] for c in cands}
                    cands += [c for c in more if c["id"] not in ids]
            scored = sorted(
                ((score(qname, qabv, qdec, c), c) for c in cands),
                key=lambda x: -x[0])
            if not scored:
                results.append({"input": raw, "found": False})
                continue
            top_score, top = scored[0]
            det = await bottle_details(page, top["id"])
            await page.wait_for_timeout(DELAY)
            margin = top_score - (scored[1][0] if len(scored) > 1 else 0)
            conf = max(5, min(99, top_score + min(margin, 20) / 4))
            alts = [{"wb_id": c["id"], "name": c["name"],
                     "strength": c["strength"], "bottled": c["bottled"],
                     "url": BOTTLE.format(id=c["id"])}
                    for _, c in scored[1:4] if top_score < 60 or _ < 40]
            results.append({
                "input": raw, "found": True, "wb_id": top["id"],
                "name": det["name"] or top["name"],
                "rating": det["rating"], "votes": det["votes"],
                "abv": det["abv"], "lowest_price_eur": det["lowest_price_eur"],
                "shops": det["shops"], "confidence": round(conf),
                "url": BOTTLE.format(id=top["id"]),
                "alternatives": alts,
            })
        await page.close()
        return results


if __name__ == "__main__":
    lines = [l.strip() for l in sys.stdin if l.strip()]
    res = asyncio.run(main(lines))
    res.sort(key=lambda r: (r.get("rating") is not None, r.get("rating") or 0),
             reverse=True)
    fields = ["input", "found", "name", "rating", "votes",
              "abv", "lowest_price_eur", "shops", "confidence",
              "wb_id", "url", "alternatives"]
    with open("results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in res:
            row = dict(r)
            row["alternatives"] = json.dumps(row.get("alternatives", []))
            w.writerow({k: row.get(k) for k in fields})

    cols = [("input", "Input", 36), ("name", "Match", 28),
            ("rating", "Rating", 6), ("votes", "Votes", 5),
            ("abv", "ABV", 5), ("price", "Price €", 8),
            ("confidence", "Conf%", 5), ("url", "Whiskybase link", 0)]
    def cell(r, k):
        if k == "price":
            v = r.get("lowest_price_eur")
            return f"€{v}" if v else "—"
        v = r.get(k)
        return "—" if v in (None, "") else str(v)
    widths = [(k, t, min(w, max(len(t), *(len(cell(r, k)) for r in res))) if w else None)
              for k, t, w in cols]
    print(" | ".join(t.ljust(w) if w else t for (_, t, w) in widths))
    print("-+-".join("-" * w if w else "-" * len(t) for (_, t, w) in widths))
    for r in res:
        print(" | ".join(cell(r, k)[:w].ljust(w) if w else cell(r, k)
                        for (k, _, w) in widths))
        for a in r.get("alternatives", []):
            ab = a.get("strength") or "?"
            print(f"{'':36}   alt: {a['name'][:50]} ({ab}%) {a['url']}")
    print()
    print(json.dumps(res, indent=2))
