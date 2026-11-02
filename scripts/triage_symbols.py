#!/usr/bin/env python3
"""
Interactive triage of the leader-enabled math symbols and emoji.

Why this exists
---------------
The generated `.dtsi` files carry roughly 2400 entries of which ~1000 are
enabled. Choosing that set by editing the files means scrolling past a thousand
commented lines, and the only feedback is a rebuild. This serves a local page
listing every candidate with its glyph, its typst name and its leader sequence,
and a toggle per row.

Where the truth lives
---------------------
The `.dtsi` files, not this script. On start they are parsed to learn which
entries are currently enabled; the page holds that state in memory while you
work; on submit the files are rewritten in place, commenting lines in or out,
and the server exits. So there is no separate state file to keep in sync, and
the generator reads the same files back - see read_enabled() there.

Usage
-----
    ./scripts/triage_symbols.py                 # math, then emoji, on :8000
    ./scripts/triage_symbols.py --category math
    ./scripts/triage_symbols.py --port 9000

Nothing is written until you press Submit. Ctrl-C leaves the files untouched.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import pathlib
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REPO = pathlib.Path(__file__).resolve().parent.parent

# Reuse the generator rather than duplicating its typst parsing and its
# section weighting, which decide the order symbols are presented in.
_spec = importlib.util.spec_from_file_location(
    "gen_leader_symbols", REPO / "scripts" / "gen_leader_symbols.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

# Each leader sequence costs this much RAM, from struct leader_seq_cfg with
# MAX_KEYS_PER_SEQUENCE = 32: 16 bytes of header plus 4 per key slot, in .data.
BYTES_PER_SEQUENCE = 16 + 4 * 32

# The largest set known to link: 1000 sequences, roughly 141 KB of the 256 KB
# available after ZMK's own BLE and Studio baseline. Going past this is what
# overflowed the linker last time, so it is the warning threshold.
KNOWN_GOOD = 1000

VS = (0xFE0E, 0xFE0F)


def node_name(cat: str, used: str) -> str:
    """The devicetree node name for a used spelling, as emit_selected writes it."""
    return f"seq_{cat}_" + re.sub(r"[^A-Za-z0-9_]", "_", used)


def load_category(category: str) -> dict:
    """Everything the page needs: every candidate, and which are enabled."""
    if category == "math":
        sym_path = gen.fetch("sym.txt", offline=False)
        sections = gen.build_sections(sym_path)
        entries = [
            (n, sp)
            for n, sp in gen.parse_codex(sym_path)
            if not any(k in sections.get(n, "") for k in gen.EXCLUDED_SECTIONS)
        ]
        entries.sort(key=lambda e: gen.usefulness(e[0], sections.get(e[0], "")))
        cat, prefix, limit = "m", "M", 500
        dtsi = REPO / "config" / "include" / "leader-math.dtsi"
        unused = set()
    else:
        entries = list(gen.parse_codex(gen.fetch("emoji.txt", offline=False)))
        entries.sort(key=gen.emoji_rank)
        cat, prefix, limit = "e", "E", 451
        dtsi = REPO / "config" / "include" / "leader-emoji.dtsi"
        unused = set()

    enabled = gen.read_enabled(dtsi, cat)

    rows = []
    for typst, spec in entries:
        cps = gen.spec_to_codepoints(spec)
        if not cps:
            continue
        if category == "emoji" and gen.is_button_glyph(cps):
            continue  # labelled buttons, never offered
        glyph = "".join(chr(c) for c in cps if c not in VS)
        used = typst
        needs_dot = False
        rows.append(
            {
                "typst": typst,
                "used": used,
                "glyph": glyph,
                "on": typst in enabled,
                "node": node_name(cat, used),
            }
        )

    # The trailing-DOT decision depends on the whole enabled set, so it is only
    # shown for entries that are on. For the rest the sequence is indicative.
    on_names = [r["typst"] for r in rows if r["on"]]
    dots = gen.dot_needed(on_names, prefix)
    for r in rows:
        r["seq"] = " ".join(gen.emitted_keys(r["used"], prefix, r["typst"] in dots))
        r["needs_dot"] = r["typst"] in dots

    return {
        "category": category,
        "cat": cat,
        "prefix": prefix,
        "rows": rows,
        "dtsi": dtsi,
        "enabled_count": sum(1 for r in rows if r["on"]),
    }


PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Leader symbol triage &mdash; {category}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 14px/1.5 system-ui, sans-serif; margin: 0; }}
  header {{ position: sticky; top: 0; background: canvas; padding: .6rem 1rem;
            border-bottom: 1px solid color-mix(in srgb, canvastext 20%, transparent);
            display: flex; gap: 1rem; align-items: baseline; flex-wrap: wrap; }}
  h1 {{ font-size: 1rem; margin: 0; }}
  #count {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  #ram {{ color: color-mix(in srgb, canvastext 60%, transparent); }}
  #warn {{ color: #b00; font-weight: 600; display: none; }}
  #filters {{ padding: .4rem 1rem; display: flex; gap: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .25rem .6rem; border-bottom: 1px solid
            color-mix(in srgb, canvastext 12%, transparent); }}
  th {{ position: sticky; top: 3.2rem; background: canvas; }}
  td.glyph {{ font-size: 1.4rem; width: 3rem; }}
  td.seq {{ font-family: ui-monospace, monospace; white-space: nowrap; }}
  tr.off {{ opacity: .45; }}
  input[type=checkbox] {{ width: 1.2rem; height: 1.2rem; }}
  #submit {{ position: fixed; right: 1rem; bottom: 1rem; padding: .7rem 1.4rem;
             font-size: 1rem; font-weight: 600; }}
</style>
<header>
  <h1>Leader triage &mdash; {category}</h1>
  <span>enabled <span id="count">{enabled_count}</span> of {total}</span>
  <span id="ram"></span>
  <span id="warn">over the known-good size &mdash; this may not link</span>
</header>
<div id="filters">
  <label><input type="checkbox" id="onlyoff"> show only disabled</label>
  <label><input type="checkbox" id="onlyon"> show only enabled</label>
  <label>filter name <input id="namefilter" placeholder="arrow, heart, ..."></label>
</div>
<table>
  <thead><tr><th>keep</th><th>glyph</th><th>typst name</th><th>leader sequence</th></tr></thead>
  <tbody id="rows">
  {rows}
  </tbody>
</table>
<button id="submit">Submit and write .dtsi</button>
<script>
// Everything runs after the document is fully parsed. The page is ~280 KB with
// 1355 rows, and the script sits at the very end: binding synchronously left
// later rows unparsed on a slower (network) load, so getElementById returned
// null for them, the loop threw, and only the early rows stayed bound - which
// is what made the list appear to re-sort and the filters appear dead.
document.addEventListener('DOMContentLoaded', () => {{
const ROWS = {rows_json};
const BYTES = {bytes_per_seq};
const KNOWN_GOOD = {known_good};
const cat = {cat_json};

const tbody = document.getElementById('rows');
const countEl = document.getElementById('count');
const ramEl = document.getElementById('ram');
const warnEl = document.getElementById('warn');

function refresh() {{
  let on = 0;
  for (const r of ROWS) {{ if (r.on) on++; }}
  countEl.textContent = on;
  ramEl.textContent = (on * BYTES / 1024).toFixed(0) + ' KB RAM';
  warnEl.style.display = on > KNOWN_GOOD ? 'inline' : 'none';

  const onlyOff = document.getElementById('onlyoff').checked;
  const onlyOn  = document.getElementById('onlyon').checked;
  const q = document.getElementById('namefilter').value.toLowerCase();
  // Hide rows by walking the table, not by id lookup, so one missing row cannot
  // abort the loop and leave everything after it unfiltered.
  let i = 0;
  for (const tr of tbody.querySelectorAll('tr')) {{
    const r = ROWS[i++];
    if (!r) continue;
    tr.classList.toggle('off', !r.on);
    let show = true;
    if (onlyOff && r.on) show = false;
    if (onlyOn && !r.on) show = false;
    if (q && !r.typst.toLowerCase().includes(q)) show = false;
    tr.style.display = show ? '' : 'none';
  }}
}}

// Bind by walking the DOM rather than looking each row up by id.
//
// The id lookup threw `cb is null` on the emoji page: a single failed
// getElementById aborted the whole loop, so every later row was left unbound.
// The visible symptom was the list appearing to re-sort, because only the
// early rows still responded to the filters.
//
// Indexing the <tr> elements directly removes the lookup, and therefore the
// name-to-id matching that can go wrong on a large page.
const trs = tbody.querySelectorAll('tr');
for (let i = 0; i < ROWS.length; i++) {{
  const r = ROWS[i];
  const tr = trs[i];
  if (!tr) continue;
  const cb = tr.querySelector('input[type=checkbox]');
  if (!cb) continue;
  cb.checked = r.on;
  cb.addEventListener('change', () => {{ r.on = cb.checked; refresh(); }});
}}
for (const id of ['onlyoff', 'onlyon', 'namefilter']) {{
  const el = document.getElementById(id);
  if (el) el.addEventListener('input', refresh);
}}
refresh();
}});  // end DOMContentLoaded

document.getElementById('submit').addEventListener('click', async () => {{
  const btn = document.getElementById('submit');
  btn.disabled = true; btn.textContent = 'writing...';
  const res = await fetch('/submit', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{category: cat, enabled: ROWS.filter(r => r.on).map(r => r.typst)}})
  }});
  const out = await res.json();
  document.body.innerHTML = '<pre style="padding:2rem;font-size:1rem">' +
    (out.message || out.error) + '</pre>';
}});
</script>
</html>
"""


def render(state: dict) -> str:
    rows = []
    for r in state["rows"]:
        tr = (
            f'<tr id="{html.escape(r["typst"])}" class="{"on" if r["on"] else "off"}">'
            f'<td><input type="checkbox" {"checked" if r["on"] else ""}></td>'
            f'<td class="glyph">{html.escape(r["glyph"]) or "&nbsp;"}</td>'
            f'<td><code>{html.escape(r["typst"])}</code></td>'
            f'<td class="seq">{html.escape(r["seq"])}</td>'
            f"</tr>"
        )
        rows.append(tr)
    return PAGE.format(
        category=state["category"],
        total=len(state["rows"]),
        enabled_count=state["enabled_count"],
        rows="\n".join(rows),
        rows_json=json.dumps(
            [{"typst": r["typst"], "on": r["on"]} for r in state["rows"]]
        ),
        bytes_per_seq=BYTES_PER_SEQUENCE,
        known_good=KNOWN_GOOD,
        cat_json=json.dumps(state["cat"]),
    )


def rewrite_dtsi(state: dict, enabled: set) -> str:
    """Comment in or out the sequence lines of one .dtsi, in place.

    Only the leading `// ` is added or removed: nothing else on the line is
    touched, so the generated spelling, bindings and glyph comment all survive
    exactly as the generator wrote them.
    """
    path = state["dtsi"]
    text = path.read_text(encoding="utf-8")
    cat = state["cat"]
    changed = {"on": 0, "off": 0}

    def fix(match: re.Match) -> str:
        indent, commented, node, rest = match.group(1, 2, 3, 4)
        # The node name has dots replaced by underscores, so map it back before
        # comparing with the enabled set, which holds typst names.
        typst = node[len(f"seq_{cat}_") :].replace("_", ".")
        want = typst in enabled
        was = bool(commented)
        if want and was:
            changed["on"] += 1
            return f"{indent}{node}{rest}"
        if not want and not was:
            changed["off"] += 1
            return f"{indent}// {node}{rest}"
        return match.group(0)

    # The whitespace before '{' is part of group 4, not a bare separator: if it
    # is dropped, the rewrite emits `seq_m_eq{` and the devicetree fails to
    # parse. Group 3 is the node name alone, group 4 the rest of the line.
    pattern = re.compile(
        rf"^([ \t]*)(// )?(seq_{cat}_\w+)(\s+\{{ sequence = <[^>]+>; "
        rf"bindings = <[^>]+>; \}};.*)$",
        re.M,
    )
    text = pattern.sub(fix, text)
    path.write_text(text, encoding="utf-8")
    return (
        f"Wrote {path.relative_to(REPO)}\n\n"
        f"  {changed['on']} enabled\n"
        f"  {changed['off']} disabled\n"
        f"  {len(enabled)} enabled in total\n\n"
        f"Next:\n"
        f"  ./scripts/gen_leader_symbols.py      # regenerate the .dtsi and docs\n"
        f"  git diff config/include/             # review\n"
    )


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 with an explicit Content-Length, rather than the default 1.0 that
    # closes the socket per response. The page is ~280 KB, and a predictable
    # framed body is easier for the browser to hand to the parser in one piece.
    protocol_version = "HTTP/1.1"

    state: dict = {}

    def log_message(self, *_args) -> None:  # quieter console
        pass

    def do_GET(self) -> None:  # noqa: N802
        body = render(self.state).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/submit":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        enabled = set(payload.get("enabled") or [])

        known = {r["typst"] for r in self.state["rows"]}
        unknown = sorted(enabled - known)
        if unknown:
            reply = {"error": f"unknown names: {unknown[:5]}"}
        else:
            reply = {"message": rewrite_dtsi(self.state, enabled)}

        body = json.dumps(reply).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--category", choices=("math", "emoji"), default="math")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    state = load_category(args.category)
    Handler.state = state

    url = f"http://0.0.0.0:{args.port}/"
    print(f"  {args.category}: {len(state['rows'])} candidates, "
          f"{state['enabled_count']} enabled")
    print(f"  serving {url}  (Ctrl-C to abort without writing anything)")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  aborted, nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
