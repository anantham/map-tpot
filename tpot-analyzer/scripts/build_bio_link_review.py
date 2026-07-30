#!/usr/bin/env python3
"""Render resolved bio links as a browsable review gallery.

Reads ``bio_link_profile`` (populated by ``resolve_bio_links.py``) and emits a
self-contained HTML page: preview image, title, classifier verdict with its
reasons, off-platform identity links, and a text excerpt — so a human can tell a
personal blog from a work site at a glance instead of trusting the heuristic.

Images are referenced by URL, not embedded; the browser fetches them lazily and
a broken one simply collapses.

Usage:
    python scripts/build_bio_link_review.py -o ~/Downloads/bio-links.html
"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "archive_tweets.db"

CSS = """
:root{--bg:#fbfaf8;--panel:#fff;--ink:#16130f;--dim:#6b6157;--line:#e6e0d8;
--accent:#3f5bb5;--good:#1f7a4d;--warn:#9a6408;--bad:#b2384e;--mono:ui-monospace,Menlo,monospace}
@media(prefers-color-scheme:dark){:root{--bg:#131211;--panel:#1c1a18;--ink:#eee9e2;
--dim:#a09589;--line:#2f2b27;--accent:#9db0ee;--good:#5fc48d;--warn:#e2b464;--bad:#ef8b9c}}
:root[data-theme=dark]{--bg:#131211;--panel:#1c1a18;--ink:#eee9e2;--dim:#a09589;
--line:#2f2b27;--accent:#9db0ee;--good:#5fc48d;--warn:#e2b464;--bad:#ef8b9c}
:root[data-theme=light]{--bg:#fbfaf8;--panel:#fff;--ink:#16130f;--dim:#6b6157;
--line:#e6e0d8;--accent:#3f5bb5;--good:#1f7a4d;--warn:#9a6408;--bad:#b2384e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 80px}
h1{font-size:21px;margin:0 0 6px}p.lede{color:var(--dim);margin:0;max-width:70ch}
.tally{font:12.5px/1.7 var(--mono);color:var(--dim);border-top:1px solid var(--line);
border-bottom:1px solid var(--line);padding:10px 0;margin:16px 0}
.tally b{color:var(--ink)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}
.filters button{font:600 11px/1 var(--mono);letter-spacing:.05em;padding:7px 11px;
border:1px solid var(--line);border-radius:99px;background:var(--panel);color:var(--dim);cursor:pointer}
.filters button:hover{color:var(--ink)}
.filters button[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;
overflow:hidden;display:flex;flex-direction:column}
.shot{width:100%;aspect-ratio:1.9;object-fit:cover;background:var(--bg);
border-bottom:1px solid var(--line);display:block}
.noshot{width:100%;aspect-ratio:1.9;background:var(--bg);border-bottom:1px solid var(--line);
display:flex;align-items:center;justify-content:center;color:var(--line);font:11px var(--mono)}
.body{padding:13px 14px 14px;display:flex;flex-direction:column;gap:7px;flex:1}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.handle{font:600 14px var(--mono);letter-spacing:-.02em}
.handle a{color:inherit;text-decoration:none;border-bottom:1px solid var(--line)}
.handle a:hover{border-color:currentColor}
.type{font:600 10px var(--mono);letter-spacing:.06em;padding:3px 7px;border-radius:3px;
border:1px solid currentColor;white-space:nowrap}
.t-personal,.t-blog,.t-portfolio,.t-academic{color:var(--good)}
.t-newsletter,.t-creator,.t-code,.t-community{color:var(--accent)}
.t-aggregator,.t-unknown{color:var(--warn)}
.t-company,.t-dead{color:var(--bad)}
.title{font-size:13.5px;font-weight:600;line-height:1.35}
.url{font:11px var(--mono);color:var(--dim);word-break:break-all}
.url a{color:inherit}
.desc{font-size:12.5px;color:var(--dim)}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{font:10.5px var(--mono);padding:2px 6px;border-radius:3px;background:var(--bg);
border:1px solid var(--line);color:var(--dim)}
.chip.sig{color:var(--accent);border-color:var(--accent)}
details{margin-top:auto;padding-top:6px}
summary{cursor:pointer;font:11px var(--mono);color:var(--dim);letter-spacing:.03em}
summary:hover{color:var(--ink)}
.excerpt{font-size:12px;color:var(--dim);margin-top:7px;max-height:180px;overflow-y:auto;
border-left:2px solid var(--line);padding-left:9px;white-space:pre-wrap}
.why{font-size:11.5px;color:var(--dim);margin-top:6px}
.why li{margin:2px 0}
"""


def rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT * FROM bio_link_profile WHERE error IS NULL "
        "ORDER BY person_signal DESC, confidence DESC, username"
    ).fetchall()


def card(r: sqlite3.Row) -> str:
    e = html.escape
    imgs = json.loads(r["images_json"] or "[]")
    sig = json.loads(r["signal_links_json"] or "[]")
    reasons = json.loads(r["reasons_json"] or "[]")
    shot = (f'<img class="shot" loading="lazy" src="{e(imgs[0])}" alt="" '
            f'onerror="this.outerHTML=\'<div class=noshot>no preview image</div>\'">'
            if imgs else '<div class="noshot">no preview image</div>')
    hosts, seen = [], set()
    for link in sig:
        parts = link.split("/")
        h = parts[2].replace("www.", "") if len(parts) > 2 else link
        if h not in seen:
            seen.add(h)
            hosts.append(h)
    chips = "".join(f'<span class="chip sig">{e(h)}</span>' for h in hosts[:8])
    return f"""<div class="card" data-type="{e(r['site_type'] or 'unknown')}"
 data-person="{r['person_signal'] or 0}">
{shot}
<div class="body">
 <div class="top"><span class="handle"><a href="https://x.com/{e(r['username'])}"
  target="_blank" rel="noopener">@{e(r['username'])}</a></span>
  <span class="type t-{e(r['site_type'] or 'unknown')}">{e((r['site_type'] or '?').upper())}
  {r['confidence'] or 0:.2f}</span></div>
 <div class="title">{e(r['title'] or '—')}</div>
 <div class="url"><a href="{e(r['resolved_url'] or '')}" target="_blank"
  rel="noopener">{e((r['resolved_url'] or '')[:78])}</a></div>
 {f'<div class="desc">{e(r["description"][:180])}</div>' if r['description'] else ''}
 <div class="chips"><span class="chip">person {r['person_signal'] or 0:.2f}</span>{chips}</div>
 <details><summary>▸ why this verdict · page text</summary>
  <ul class="why">{''.join(f'<li>{e(x)}</li>' for x in reasons)}</ul>
  <div class="excerpt">{e((r['text_excerpt'] or '')[:900])}</div></details>
</div></div>"""


def build(conn: sqlite3.Connection) -> str:
    data = rows(conn)
    total = conn.execute("SELECT COUNT(*) FROM bio_link_profile").fetchone()[0]
    types: dict[str, int] = {}
    for r in data:
        t = r["site_type"] or "unknown"
        types[t] = types.get(t, 0) + 1
    person_like = sum(types.get(t, 0) for t in ("personal", "blog", "portfolio", "academic"))
    with_sig = sum(1 for r in data if json.loads(r["signal_links_json"] or "[]"))
    buttons = "".join(
        f'<button data-f="{t}" aria-pressed="false" onclick="flt(this)">{t} {n}</button>'
        for t, n in sorted(types.items(), key=lambda kv: -kv[1]))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bio links — site review</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Bio links — what's behind the t.co</h1>
<p class="lede">Every <code>profiles.website</code> stub resolved and fetched. The classifier is
heuristic and abstains rather than guessing, so treat <code>unknown</code> as "look yourself".
Open a card's disclosure to see the reasons and the page text.</p>
<div class="tally"><b>{len(data)}</b> of <b>{total}</b> resolved ·
<b>{person_like}</b> person-shaped (personal / blog / portfolio / academic) ·
<b>{with_sig}</b> expose off-platform identity links · generated {stamp}</div>
<div class="filters"><button data-f="all" aria-pressed="true" onclick="flt(this)">all {len(data)}</button>{buttons}</div>
<div class="grid" id="grid">{''.join(card(r) for r in data)}</div></div>
<script>
function flt(b){{
  document.querySelectorAll('.filters button').forEach(x=>x.setAttribute('aria-pressed',x===b));
  const f=b.dataset.f;
  document.querySelectorAll('.card').forEach(c=>{{
    c.style.display=(f==='all'||c.dataset.type===f)?'':'none';}});
}}
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", type=Path,
                    default=Path.home() / "Downloads" / "bio-links.html")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()
    conn = sqlite3.connect(str(args.db))
    try:
        page = build(conn)
    finally:
        conn.close()
    args.out.write_text(page, encoding="utf-8")
    print(f"✓ wrote {args.out}  ({len(page) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
