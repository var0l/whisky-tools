import csv, html, json

rows = list(csv.DictReader(open('results.csv')))
data = json.dumps(rows)

page = f'''<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Whisky results</title>
<style>
body{{font-family:system-ui,sans-serif;font-size:14px;margin:12px}}
input#f{{width:100%;box-sizing:border-box;padding:8px;margin-bottom:8px;font-size:16px}}
table{{border-collapse:collapse;width:100%}}
th{{position:sticky;top:0;background:#fff;cursor:pointer;user-select:none;border-bottom:2px solid #999;padding:6px 8px;text-align:left;white-space:nowrap}}
th .arr{{color:#999;font-size:11px}}
td{{border-bottom:1px solid #e2e2e2;padding:6px 8px;text-align:left;vertical-align:top}}
.badge{{display:inline-block;min-width:2em;text-align:center;padding:1px 6px;border-radius:8px;font-weight:600}}
.hi{{background:#d8f0d8;color:#174517}} .mid{{background:#fdeec8;color:#7a5200}} .lo{{background:#f8d7d7;color:#a22}}
tr.nf td{{color:#999}}
.altrow td{{background:#fafafa;font-size:12px;color:#555;padding:4px 8px 8px 32px}}
a{{color:#06c;text-decoration:none}}
.tgl{{cursor:pointer;color:#888;font-size:12px;white-space:nowrap}}
.num{{text-align:right}}
</style>
<input id="f" placeholder="filter… (e.g. talisker, 58.4, sftc)">
<table id="t"><thead><tr id="h"></tr></thead><tbody id="b"></tbody></table>
<script>
const COLS = [
  ["input","Input"],["confidence","Conf"],["ambiguous","Amb"],
  ["name","Match"],["rating","Rating"],["lowest_price_eur","Price €"],
  ["votes","Votes"],["abv","ABV"],["shops","Shops"],["url","Link"]];
const NUM = new Set(["confidence","rating","lowest_price_eur","votes","abv","shops"]);
const rows = {data};
let sortKey = "rating", sortDir = -1, q = "";

function badge(c) {{
  c = +c; const cls = c>=70?"hi":c>=40?"mid":"lo";
  return `<span class="badge ${{cls}}">${{c}}</span>`;
}}
function cell(r, k) {{
  if (k==="confidence") return badge(r.confidence);
  if (k==="ambiguous") return r.ambiguous==="True" ? "⚠" : "";
  if (k==="url") return `<a href="${{r.url}}">link</a>`;
  if (k==="name") return (+r.confidence<15 ? "NOT FOUND" : r.name) + altsToggle(r);
  if (k==="lowest_price_eur") return r[k] ? "€"+(+r[k]).toFixed(0) : "";
  return r[k] ?? "";
}}
function altsToggle(r) {{
  let a = []; try {{ a = JSON.parse(r.alternatives||"[]"); }} catch(e){{}}
  if (!a.length) return "";
  return ` <span class="tgl" onclick="tglAlt(this)">+${{a.length}} alt</span>`;
}}
function tglAlt(el) {{
  const tr = el.closest("tr");
  const open = tr.nextElementSibling && tr.nextElementSibling.classList.contains("altrow");
  if (open) {{ tr.nextElementSibling.remove(); el.textContent = el.textContent.replace("−","+"); return; }}
  let a = []; try {{ a = JSON.parse(tr._row.alternatives||"[]"); }} catch(e){{}}
  const td = document.createElement("tr"); td.className="altrow";
  td.innerHTML = `<td colspan="10">` + a.map(x =>
    `<a href="${{x.url}}">${{x.name.split("\\n")[0]}}</a> (${{x.strength??"?"}}%)`).join(" &nbsp;·&nbsp; ") + `</td>`;
  tr.after(td); el.textContent = el.textContent.replace("+","−");
}}
function render() {{
  document.getElementById("h").innerHTML = COLS.map(([k,t]) =>
    `<th data-k="${{k}}" onclick="sort('${{k}}')">${{t}}<span class="arr">${{sortKey===k?(sortDir>0?" ▲":" ▼"):""}}</span></th>`).join("");
  let rs = rows.filter(r => !q || JSON.stringify(r).toLowerCase().includes(q));
  rs.sort((a,b) => {{
    const nf = (+a.confidence<15) - (+b.confidence<15);
    if (nf) return nf;
    if (NUM.has(sortKey)) return ((+a[sortKey]||0)-(+b[sortKey]||0))*sortDir;
    return String(a[sortKey]).localeCompare(String(b[sortKey]))*sortDir;
  }});
  const b = document.getElementById("b");
  b.innerHTML = "";
  for (const r of rs) {{
    const tr = document.createElement("tr");
    tr._row = r;
    if (+r.confidence < 15) tr.className = "nf";
    tr.innerHTML = COLS.map(([k]) => `<td class="${{NUM.has(k)?"num":""}}">${{cell(r,k)}}</td>`).join("");
    b.appendChild(tr);
  }}
}}
function sort(k) {{ if (sortKey===k) sortDir*=-1; else {{sortKey=k;sortDir=NUM.has(k)?-1:1;}} render(); }}
document.getElementById("f").oninput = e => {{ q = e.target.value.toLowerCase(); render(); }};
render();
</script>'''
open("results.html","w").write(page)
print("ok", len(rows))
