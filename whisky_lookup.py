#!/usr/bin/env python3
"""Whiskybase lookup: given free-text whisky lines, find the matching bottle,
its rating, ABV and lowest listed shop price (EUR), plus a match-confidence
score. Drives the session's real Chrome over CDP (Cloudflare blocks plain HTTP).

Usage:  python3 whisky_lookup.py < whiskies.txt
Input lines: free text incl. ABV like "54,2%" or "58.7%", optional age
("8yo", "10 years old"), vintage year, bottler names, and Polish hints
("lata 80" = 1980s, "stare butelkowanie" = old bottling).
"""

import asyncio, csv, json, re, sys, unicodedata
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

CDP = "http://localhost:29229"
SEARCH = "https://www.whiskybase.com/search?q={q}"
BOTTLE = "https://www.whiskybase.com/whiskies/whisky/{id}"
DELAY = 1200

FX = {"€": 1.0, "£": 1.17, "$": 0.92}

# spelled-out bottler name -> Whiskybase code (and back, via token set)
ALIASES = [
    ("van wees", "vw"), ("the ultimate", "vw"),
    ("signatory", "sv"), ("signatory vintage", "sv"),
    ("cadenhead", "ca"), ("cadenhead's", "ca"), ("cadenheads", "ca"),
    ("berry bros", "br"), ("berry bros & rudd", "br"), ("bbr", "br"),
    ("jarek buss", "mswd"), ("mswd", "mswd"),
    ("the finest malts", "tfm"),
    ("whisky age", "wage"),
    ("douglas laing", "dl"),
    ("gordon macphail", "gm"), ("gordon & macphail", "gm"),
    ("gordon and macphail", "gm"),
    ("loza dzentelmenow", "lodz"), ("loża dżentelmenów", "lodz"),
    ("carn mor", "cm"), ("càrn mòr", "cm"),
    ("murray mcdavid", "mm"),
    ("scotch malt whisky society", "smws"),
    ("artist", "lmdw"), ("la maison du whisky", "lmdw"),
    ("royal mile whiskies", "rmw"),
    ("the whisky exchange", "twe"),
    ("decadent drinks", "dd"),
    ("whisky sponge", "wsp"),
    ("north star", "nss"),
    ("distilleria", "dt"),
    ("hepburn's choice", "hisp"), ("hepburns choice", "hisp"),
    ("hi-spirits", "hisp"),
    ("glenkeir", "glk"),
]


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def norm_name(s):
    s = strip_acc(s.lower())
    s = re.sub(r"['’]", "", s)
    s = re.sub(r"[^a-z0-9&]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def alias_tokens(s):
    """token set with spelled-out bottler phrases mapped to WB codes"""
    t = norm_name(s)
    for phrase, code in ALIASES:
        if phrase in t:
            t = t.replace(phrase, " " + code + " ")
    return set(re.findall(r"[a-z0-9]+", t))


def parse_line(line):
    # lines like "60% bourbon 40% sherry ... 46.0%" have several %s:
    # the bottle's ABV is the last one
    ms = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", line)
    abv = float(ms[-1].replace(",", ".")) if ms else None
    dec = None
    m = re.search(r"lata\s*(\d)\d", line, re.I) or re.search(r"\b(\d)0s\b", line)
    if m:
        dec = 1900 + int(m.group(1)) * 10
    age = None
    m = re.search(r"(\d{1,2})\s*(?:yo|y\.o\.|years?\s*old|year-old)\b", line, re.I)
    if m:
        age = int(m.group(1))
    vint = None
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20[0-2]\d)\b", line)]
    # a 4-digit year usually means the vintage (distillation year)
    if years:
        vint = min(years)
    name = re.sub(r"\d+(?:[.,]\d+)?\s*%", "", line)
    name = re.sub(r"\([^)]*\)|lata\s*\d+\.?", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name, abv, age, vint, dec


def score(qname, qabv, qage, qvint, qdec, cand):
    q, r = alias_tokens(qname), alias_tokens(cand["name"])
    overlap = len(q & r) / max(len(q), 1)
    s = 50 * overlap
    if qabv is not None and cand["strength"] is not None:
        if abs(qabv - cand["strength"]) <= 0.11:
            s += 40
        else:
            s -= 60
    if qage is not None and cand.get("age"):
        if qage == cand["age"]:
            s += 15
        elif abs(qage - cand["age"]) >= 3:
            s -= 15
    if qvint is not None and cand.get("vintage"):
        s += 10 if qvint == cand["vintage"] else -10
    if qdec is not None and cand.get("bottled"):
        s += 15 if qdec <= cand["bottled"] <= qdec + 9 else -15
    return s


def verify(qname, det):
    """page-level sanity: input's distillery tokens must appear on the page"""
    qt = alias_tokens(qname)
    page_t = alias_tokens(" ".join(filter(None, [
        det.get("name"), det.get("distillery"), det.get("bottler"),
        det.get("series")])))
    known_stop = {"ml", "vol", "cl", "single", "malt", "cask"}
    qt -= known_stop
    return len(qt & page_t) > 0


async def search_candidates(page, query):
    await page.goto(SEARCH.format(q=query), wait_until="load")
    await page.wait_for_timeout(4500)
    rows = await page.evaluate("""() => {
        const heads = [...document.querySelectorAll('thead th')].map(t => t.innerText.trim().toLowerCase());
        const idx = n => heads.indexOf(n);
        const out = [];
        document.querySelectorAll('tbody tr').forEach(tr => {
            const a = tr.querySelector('a[href*="/whiskies/whisky/"]');
            if (!a) return;
            const tds = [...tr.querySelectorAll('td')].map(t => t.innerText.trim());
            const m = a.href.match(/whiskies\\/whisky\\/(\\d+)/);
            const num = i => { const v = tds[i]; return v ? parseFloat(v.replace(',', '.')) : null; };
            const yr = i => { const m2 = (tds[i] || '').match(/(19|20)\\d{2}/); return m2 ? +m2[0] : null; };
            out.push({id: m[1], name: a.innerText.trim(),
                      strength: num(idx('strength')),
                      age: num(idx('age')),
                      bottled: yr(idx('bottled')),
                      vintage: yr(idx('vintage'))});
        });
        return out;
    }""")
    seen, cands = set(), []
    for r in rows:
        key = (r["id"], r["name"])
        if r["id"] not in seen:
            seen.add(r["id"])
            cands.append(r)
    return cands[:10]


async def google_candidates(page, brand, qabv, rare):
    """Google indexes WB pages its own search misses. Returns {id: det}."""
    q = "whiskybase " + " ".join([brand] +
        ([f"{qabv}"] if qabv else []) + rare[:3])
    await page.goto("https://www.google.com/search?q=" + quote_plus(q),
                    wait_until="load")
    await page.wait_for_timeout(3500)
    txt = await page.inner_text("body")
    ids = list(dict.fromkeys(re.findall(r"WB(\d{5,7})", txt)))
    hrefs = await page.evaluate("""() =>
        [...document.querySelectorAll('a')].map(a => a.href)
          .filter(h => h && h.includes('whiskybase'))""")
    for h in hrefs:
        m = re.search(r"whiskies/whisky/(\d+)", h)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    out = []
    for wid in ids[:6]:
        det = await bottle_details(page, wid)
        await page.wait_for_timeout(DELAY)
        out.append({"id": wid, "name": det["name"] or "",
                    "strength": det["abv"], "age": None,
                    "bottled": None, "vintage": None, "det": det})
    return out


async def bottle_details(page, wb_id):
    await page.goto(BOTTLE.format(id=wb_id), wait_until="load")
    await page.wait_for_timeout(3000)
    text = await page.inner_text("body")
    d = {"name": None, "rating": None, "votes": None, "abv": None,
         "shops": None, "lowest_price_eur": None,
         "distillery": None, "bottler": None, "series": None}
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
    for field, key in [(r"Distillery\s*\n\s*([^\n]+)", "distillery"),
                       (r"Bottler\s*\n\s*([^\n]+)", "bottler"),
                       (r"Bottling series\s*\n\s*([^\n]+)", "series")]:
        m = re.search(field, text)
        if m:
            d[key] = m.group(1).strip()
    m = re.search(r"Found (\d+) online shops?\.\s*Lowest price:\s*\n?\s*([€£$])\s*([\d.,]+)", text)
    if m:
        d["shops"] = int(m.group(1))
        d["lowest_price_eur"] = round(
            float(m.group(3).replace(",", "")) * FX.get(m.group(2), 1.0), 2)
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
                   "yo", "biblical", "peated", "fortified", "wine", "m", "h",
                   "mh", "m&h", "sc", "edition", "release", "finish",
                   "stare", "butelkowanie", "wydanie", "vintage"}
        for raw in lines:
            qname, qabv, qage, qvint, qdec = parse_line(raw)
            toks = re.findall(r"[a-z0-9&]+", qname.lower())
            brand = toks[0] if toks else ""
            rare = [t for t in toks[1:] if t not in generic]
            queries = [qname]
            if qvint:
                queries.append(f"{brand} {qvint}")
            q2 = (brand + " " + " ".join(rare)).strip()
            if q2:
                queries.append(q2)
            if qvint and rare:
                queries.append(f"{brand} {qvint} " + " ".join(rare))
            cands, ids, best_score = [], set(), -999
            for q in dict.fromkeys(queries):
                more = await search_candidates(page, quote_plus(q))
                await page.wait_for_timeout(DELAY)
                new = [c for c in more if c["id"] not in ids]
                ids.update(c["id"] for c in new)
                cands += new
                if cands:
                    best_score = max(
                        score(qname, qabv, qage, qvint, qdec, c) for c in cands)
                if best_score >= 70:
                    break
            scored = sorted(
                ((score(qname, qabv, qage, qvint, qdec, c), c) for c in cands),
                key=lambda x: -x[0])
            # Google fallback trigger: nothing found, weak match (raw score
            # <45 ≈ final conf <50), or top candidate's ABV doesn't match
            # exactly (wrong ABV ≈ wrong bottle, per user rule)
            abv_mismatch = (scored and qabv is not None
                            and scored[0][1]["strength"] is not None
                            and abs(qabv - scored[0][1]["strength"]) > 0.11)
            if not scored or scored[0][0] < 45 or abv_mismatch:
                gc = await google_candidates(page, brand, qabv, rare)
                seen = {c["id"] for c in cands}
                cands += [c for c in gc if c["id"] not in seen]
                scored = sorted(
                    ((score(qname, qabv, qage, qvint, qdec, c), c) for c in cands),
                    key=lambda x: -x[0])
            if not scored:
                results.append({"input": raw, "found": False})
                continue
            top_score, top = scored[0]
            det = top.get("det") or await bottle_details(page, top["id"])
            if not top.get("det"):
                await page.wait_for_timeout(DELAY)
            margin = top_score - (scored[1][0] if len(scored) > 1 else 0)
            conf = max(5, min(99, top_score + min(margin, 20) / 4))
            if not verify(qname, det):
                conf = min(conf, 20)
            not_found = conf < 15
            alts = [{"wb_id": c["id"], "name": c["name"],
                     "strength": c["strength"], "bottled": c["bottled"],
                     "url": BOTTLE.format(id=c["id"])}
                    for _, c in scored[1:4] if conf < 70]
            results.append({
                "input": raw, "found": not not_found, "wb_id": top["id"],
                "name": det["name"] or top["name"],
                "distillery": det["distillery"], "bottler": det["bottler"],
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
    res.sort(key=lambda r: (not r["found"], -(r.get("rating") or 0)))
    fields = ["input", "confidence", "name", "rating", "lowest_price_eur",
              "url", "votes", "abv", "shops", "wb_id", "alternatives"]
    with open("results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in res:
            row = dict(r)
            row["alternatives"] = json.dumps(row.get("alternatives", []))
            w.writerow({k: row.get(k) for k in fields})

    cols = [("input", "Input", 36), ("confidence", "Conf%", 5),
            ("name", "Match", 28), ("rating", "Rating", 6),
            ("price", "Price €", 8), ("url", "Whiskybase link", 0)]
    def cell(r, k):
        if k == "price":
            v = r.get("lowest_price_eur")
            return f"€{v}" if v else "—"
        if k == "name" and not r.get("found", True):
            return "NOT FOUND"
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
