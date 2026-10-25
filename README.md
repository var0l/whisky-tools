# whisky-tools

Tooling for evaluating a whisky tasting event: given a pasted list of
whiskies (free text + ABV), find each bottle on
[Whiskybase](https://www.whiskybase.com) and report its community rating,
vote count, ABV, lowest shop price and a match-confidence score.

## Goals

- **Input**: free-text lines as published by event organisers, e.g.
  `M&H APEX TERROIR DEAD SEA 57,4%` or
  `Talisker 10 years old 45.8% (stare butelkowanie lata 70.)`.
  Includes Polish annotations ("lata 80" = bottled in the 1980s,
  "stare butelkowanie" = old bottling), typos and mixed separators.
- **Output**: a table sorted by rating (desc) with columns
  input / match / rating / votes / ABV / price in EUR / confidence% /
  Whiskybase link. Low-confidence rows list up to 3 clickable alternatives.
  CSV (`results.csv`) written alongside stdout.
- **Correctness over coverage**: the event bottles are very specific
  (distillery + bottler + vintage + ABV + cask). An ABV mismatch means
  it's almost certainly the wrong bottle — scoring treats it as near-fatal.
- Results feed a real tasting event (~30-50 bottles); the user cares about
  the output table, not the code.

## How it works

- Whiskybase has no public free API and sits behind Cloudflare (plain
  HTTP returns a 403 challenge). The script drives a **real Chrome via
  CDP** (`http://localhost:29229`). In a Devin session this is the
  session's own Chrome; outside, run
  `chrome --remote-debugging-port=29229` and pass the Cloudflare check once.
- Pipeline per line: parse name + ABV + decade hint → Whiskybase search →
  candidate rows (name, strength, bottled year) → score → open the top
  candidate's page → extract rating, votes, ABV, lowest shop listing →
  confidence = weighted score (name-token overlap +55, exact ABV +45,
  ABV mismatch −60, decade match ±15, margin bonus).
- Fallback search: when the first query yields <3 candidates or a weak
  top score, re-search with brand + rare tokens (drops generic words like
  APEX/terroir/single cask).
- Prices: lowest **anonymous** shop listing, converted to EUR with
  hardcoded rates (£×1.17, $×0.92). Logged-in users see ~5x more listings.

## Usage

    pip install playwright
    python3 whisky_lookup.py < input2.txt

`input.txt` = 6-bottle sample (M&H); `input2.txt` = real 46-bottle event
list; `results.csv` = latest run output.

## Change history

- **v1** — basic search + bottle-page scrape; JSON + CSV output.
- **v2** — fixed `&` in names breaking the search URL (quote_plus);
  fallback query for sparse results; stdout table with Whiskybase link.
- **v3** — sort by rating desc; strict-ABV scoring (−60 on mismatch);
  decade hints ("lata XX") scored against the bottled-year column;
  EUR-only prices (hardcoded FX); top-3 alternatives on low-confidence rows.
- **v4** — bottler alias table (vW/SV/CA/BR/MSWD/TFM/WAGE/DL/GM/LoDz/CM/
  SMWS/LMDW…); age+vintage scoring; page-level verification; "NOT FOUND"
  below conf 15 and sorted to the bottom; columns reordered
  (input/confidence/name/rating/price/link).
- **v5** — multi-query search: full line → `brand + vintage` →
  `brand + rare tokens` → combined, stops early at conf ≥70. **Google
  fallback**: when WB search fails, queries
  `whiskybase {brand} {abv} {rare tokens}` on Google and extracts WB ids
  from the results page — Google indexes bottles WB's own search misses
  (Ballechin 2014 "Foundations", Kilkerran Heavily Peated PiP6, Mosgaard
  peated batches). Real-list result: 46/46 found.

## Known gaps / next steps

- Some rows remain low-confidence (roughly 20-60) — genuinely ambiguous
  bottles; check the clickable alternatives.
- Bottled-year scoring takes the max year in the row — vintage vs bottled
  column could be separated for precision.
- Optional: logged-in Whiskybase session for the full shop-listing table.
- Optional: second price source (auction/retail) for bottles with no
  Whiskybase listings.

## Session notes

Development happens on a Devin VM; the browser used is that machine's
Chrome (already past Cloudflare). Run commands from this repo or
`~/whisky/`.
