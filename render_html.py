import csv, html, json

rows = list(csv.DictReader(open('results.csv')))
data = json.dumps(rows)

page = f'''<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Whisky results</title>
<style>
body{{font-family:system-ui,sans-serif;font-size:14px;margin:12px}}
input#f{{width:100%;box-sizing:border-box;padding:8px;margin-bottom:6px;font-size:16px}}
#colsel{{margin-bottom:8px;font-size:12px}}
#colsel label{{margin-right:10px;white-space:nowrap;cursor:pointer}}
table{{border-collapse:collapse;width:100%}}
th{{position:sticky;top:0;background:#fff;cursor:pointer;user-select:none;border-bottom:2px solid #999;padding:6px 8px;text-align:left;white-space:nowrap}}
th .arr{{color:#999;font-size:11px}}
td{{border-bottom:1px solid #e2e2e2;padding:6px 8px;text-align:left;vertical-align:top}}
.badge{{display:inline-block;min-width:2em;text-align:center;padding:1px 6px;border-radius:8px;font-weight:600}}
.hi{{background:#d8f0d8;color:#174517}} .mid{{background:#fdeec8;color:#7a5200}} .lo{{background:#f8d7d7;color:#a22}}
tr.nf td{{color:#999}}
.altrow td,.xrow td{{background:#fafafa;font-size:12px;color:#555;padding:4px 8px 8px 32px}}
a{{color:#06c;text-decoration:none}}
.tgl{{cursor:pointer;color:#888;font-size:12px;white-space:nowrap}}
.num{{text-align:right}}
#nfhead{{cursor:pointer;margin:14px 0 6px;color:#666;font-weight:600}}
.parts{{color:#666}}
.parts .neg{{color:#b00}}
</style>
<input id="f" placeholder="filter… (e.g. talisker, 58.4, sftc)">
<div id="colsel"></div>
<table id="t"><thead><tr id="h"></tr></thead><tbody id="b"></tbody></table>
<div id="nfhead" onclick="toggleNF()">▸ NOT FOUND (<span id="nfc"></span>) — tap to expand</div>
<table id="nft" style="display:none"><thead><tr id="nfh"></tr></thead><tbody id="nfb"></tbody></table>
<script>
const COLS = [
  ["input","Input",1],["confidence","Conf",1],["ambiguous","Amb",0],
  ["name","Match",1],["rating","Rating",1],["lowest_price_eur","Price €",1],
  ["votes","Votes",0],["abv","ABV",1],["shops","Shops",0],["url","Link",1]];
const NUM = new Set(["confidence","rating","lowest_price_eur","votes","abv","shops"]);
const rows = {data};
let visible = {{}}; COLS.forEach(([k,,d]) => visible[k]=!!d);
let sortKey = "rating", sortDir = -1, q = "";

const cs = document.getElementById("colsel");
for (const [k,t] of COLS) {{
  const lb = document.createElement("label");
  lb.innerHTML = `<input type="checkbox" ${{visible[k]?"checked":""}} onchange="visible['${{k}}']=this.checked;render()"> ${{t}}`;
  cs.appendChild(lb);
}}

function badge(c) {{
  c = +c; const cls = c>=70?"hi":c>=40?"mid":"lo";
  return `<span class="badge ${{cls}}">${{c}}</span>`;
}}
function altsToggle(r) {{
  let a = []; try {{ a = JSON.parse(r.alternatives||"[]"); }} catch(e){{}}
  if (!a.length) return "";
  return ` <span class="tgl" onclick="tglAlt(this)">+${{a.length}} alt</span>`;
}}
function explain(r) {{
  let p = {{}}; try {{ p = JSON.parse(r.score_parts||"{{}}"); }} catch(e){{}}
  const items = Object.entries(p).map(([k,v]) =>
    typeof v==="number" ? `<span class="${{v<0?"neg":""}}">${{k}} ${{v>0?"+":""}}${{v}}</span>` : `${{k}}: ${{v}}`);
  return `<span class="tgl" onclick="tglX(this)">explain</span><span class="parts" style="display:none"> · ${{items.join(" · ")}}</span>`;
}}
function cell(r, k) {{
  if (k==="confidence") return badge(r.confidence) + " " + explain(r);
  if (k==="ambiguous") return r.ambiguous==="True" ? "⚠" : "";
  if (k==="url") return `<a href="${{r.url}}">link</a>`;
  if (k==="name") return (+r.confidence<15 ? "NOT FOUND" : r.name) + altsToggle(r);
  if (k==="lowest_price_eur") return r[k] ? "€"+(+r[k]).toFixed(0) : "";
  return r[k] ?? "";
}}
function tglX(el) {{
  const p = el.nextElementSibling;
  p.style.display = p.style.display==="none" ? "inline" : "none";
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
const visCols = () => COLS.filter(([k]) => visible[k]);
function header(el) {{
  el.innerHTML = visCols().map(([k,t]) =>
    `<th data-k="${{k}}" onclick="sort('${{k}}')">${{t}}<span class="arr">${{sortKey===k?(sortDir>0?" ▲":" ▼"):""}}</span></th>`).join("");
}}
function rowHtml(r) {{
  return visCols().map(([k]) => `<td class="${{NUM.has(k)?"num":""}}">${{cell(r,k)}}</td>`).join("");
}}
function render() {{
  header(document.getElementById("h"));
  header(document.getElementById("nfh"));
  let rs = rows.filter(r => !q || JSON.stringify(r).toLowerCase().includes(q));
  rs.sort((a,b) => {{
    if (NUM.has(sortKey)) return ((+a[sortKey]||0)-(+b[sortKey]||0))*sortDir;
    return String(a[sortKey]).localeCompare(String(b[sortKey]))*sortDir;
  }});
  const b = document.getElementById("b"), nfb = document.getElementById("nfb");
  b.innerHTML = ""; nfb.innerHTML = "";
  let nfc = 0;
  for (const r of rs) {{
    const tr = document.createElement("tr");
    tr._row = r;
    if (+r.confidence < 15) {{ tr.className = "nf"; nfb.appendChild(tr); nfc++; }}
    else b.appendChild(tr);
    tr.innerHTML = rowHtml(r);
  }}
  document.getElementById("nfc").textContent = nfc;
  document.getElementById("nfhead").style.display = nfc ? "block" : "none";
}}
function toggleNF() {{
  const t = document.getElementById("nft"), h = document.getElementById("nfhead");
  const open = t.style.display !== "none";
  t.style.display = open ? "none" : "table";
  h.firstChild.textContent = (open ? "▸ " : "▾ ") + "NOT FOUND (" + nfcCount() + ") — tap to expand";
}}
function nfcCount() {{ return document.getElementById("nfc").textContent; }}
function sort(k) {{ if (sortKey===k) sortDir*=-1; else {{sortKey=k;sortDir=NUM.has(k)?-1:1;}} render(); }}
document.getElementById("f").oninput = e => {{ q = e.target.value.toLowerCase(); render(); }};
render();
</script>'''
open("results.html","w").write(page)
print("ok", len(rows))
