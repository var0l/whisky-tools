# whisky-tools

`whisky_lookup.py` — given a pasted list of whiskies (free text + ABV),
finds the matching bottle on Whiskybase and outputs a table with the
matched name, community rating, vote count, ABV, lowest shop price (EUR),
a match-confidence score and the Whiskybase link.

## Usage

    pip install playwright
    python3 whisky_lookup.py < input2.txt

Notes:
- It drives a real Chrome over CDP (`localhost:29229`) because Whiskybase
  sits behind Cloudflare — plain HTTP gets a 403. Point `CDP` at your own
  `chrome --remote-debugging-port` if needed.
- Prices are lowest anonymous shop listings, converted to EUR with
  hardcoded rates (£1.17, $0.92 per unit).
- Low-confidence rows print up to 3 alternative candidates.
- Understands decade hints like "lata 80" / "(stare butelkowanie lata 70.)".

`input.txt` / `input2.txt` are sample whisky lists; `results.csv` is the
latest output.
