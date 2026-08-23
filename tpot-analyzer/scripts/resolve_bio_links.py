#!/usr/bin/env python3
"""Resolve profile bio links and classify the pages behind them.

The ``profiles.website`` column stores unresolved ``t.co`` stubs and nothing
reads it. This script resolves each stub to its destination, fetches the page
through the existing SSRF-guarded ``safe_urlopen``, and records what kind of
site it is plus the outbound identity links it exposes.

Why this matters: a personal site links to GitHub, Substack, arXiv, a sangha —
affiliation and competence evidence the X follow graph structurally cannot
contain. Accounts whose substance lives off-platform are currently invisible to
all three existing channels (follows, engagement, tweet text).

Usage
-----
    python scripts/resolve_bio_links.py --limit 10        # small probe first
    python scripts/resolve_bio_links.py --url https://girl.surgery/
    python scripts/resolve_bio_links.py                   # full run
    python scripts/resolve_bio_links.py --report          # read back, no network
    python scripts/resolve_bio_links.py --reclassify      # re-derive from cache

Raw HTML is cached per row, so tuning the classifier costs nothing: ``--reclassify``
re-runs extraction and scoring offline and prints how the verdicts moved.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.tweet_enrichment import resolve_tco_url  # noqa: E402
from src.api.url_guard import safe_urlopen  # noqa: E402
from src.enrichment import (  # noqa: E402
    classify, extract, redirect_target, safe_host, urls_in_text,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "archive_tweets.db"
# t.co returns an HTTP 301 to terse agents but a JS interstitial to browsers.
# The interstitial is BETTER: it names the destination without contacting it, so
# a dead or hostile target still yields the URL the account pointed at.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# Raw HTML is kept so the classifier can be re-derived offline. Without it every
# tweak to a regex would mean re-fetching ~1,600 real people's servers.
HTML_CAP = 300_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS bio_link_profile (
    account_id     TEXT NOT NULL,
    username       TEXT,
    source_url     TEXT NOT NULL,
    resolved_url   TEXT,
    site_type      TEXT,
    confidence     REAL,
    person_signal  REAL,
    is_reviewable  INTEGER,
    title          TEXT,
    description    TEXT,
    og_image       TEXT,
    images_json    TEXT,
    signal_links_json TEXT,
    paths_json     TEXT,
    reasons_json   TEXT,
    text_excerpt   TEXT,
    error          TEXT,
    html_gz        BLOB,
    html_bytes     INTEGER,
    derived_at     TEXT,
    fetched_at     TEXT NOT NULL,
    PRIMARY KEY (account_id, source_url)
);
CREATE INDEX IF NOT EXISTS idx_bio_link_type ON bio_link_profile(site_type);
CREATE INDEX IF NOT EXISTS idx_bio_link_account ON bio_link_profile(account_id);
"""


def connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # Additive migration: the first version of this table had no raw-HTML cache.
    have = {r["name"] for r in conn.execute("PRAGMA table_info(bio_link_profile)")}
    for col, decl in (("html_gz", "BLOB"), ("html_bytes", "INTEGER"),
                      ("derived_at", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE bio_link_profile ADD COLUMN {col} {decl}")
    conn.commit()
    return conn


def candidates(conn) -> list[tuple[str, str, str]]:
    """Every (account_id, username, url) we can probe, best source first.

    The ``website`` column is populated for only 230 of 26,098 profiles, but
    1,369 bios carry a URL in their text. Mining both yields 2,114 distinct URLs
    across 1,571 accounts.

    Every URL is kept, not just the first: 379 accounts list two or more, and the
    entire tail is unresolved ``t.co`` — so a dropped link could be a GitHub, a
    Substack or a personal site we would never see. The explicit website field is
    ordered first; bio links follow in the order they appear.
    """
    names: dict[str, str] = {}
    urls: dict[str, list[str]] = {}

    def add(account_id: str, username: str, url: str) -> None:
        names.setdefault(account_id, username)
        bucket = urls.setdefault(account_id, [])
        if url not in bucket:
            bucket.append(url)

    for row in conn.execute(
        "SELECT account_id, username, website FROM profiles "
        "WHERE website IS NOT NULL AND website <> ''"
    ):
        add(row["account_id"], row["username"], row["website"])
    for row in conn.execute(
        "SELECT account_id, username, bio FROM profiles WHERE bio LIKE '%http%' "
        "UNION ALL "
        "SELECT account_id, username, bio FROM resolved_accounts WHERE bio LIKE '%http%'"
    ):
        for url in urls_in_text(row["bio"], limit=12):
            add(row["account_id"], row["username"], url)

    return sorted(
        ((aid, names.get(aid) or "", u) for aid, bucket in urls.items() for u in bucket),
        key=lambda r: (r[1], r[2]))


def pending(conn, limit: int | None, refetch: bool) -> list[tuple[str, str, str]]:
    done: set[tuple[str, str]] = set()
    if not refetch:
        done = {(r[0], r[1]) for r in conn.execute(
            "SELECT account_id, source_url FROM bio_link_profile "
            "WHERE error IS NULL AND html_gz IS NOT NULL")}
    rows = [c for c in candidates(conn) if (c[0], c[2]) not in done]
    return rows[:limit] if limit else rows


def _get(url: str, timeout: int) -> tuple[str, str]:
    """Fetch one URL. Returns (final_url, html). Raises on any failure."""
    resp = safe_urlopen(url, timeout=timeout, headers={"User-Agent": UA})
    return getattr(resp, "url", url), resp.read(600_000).decode("utf-8", "replace")


def probe(source_url: str, timeout: int = 15) -> tuple[dict, str | None]:
    """Resolve a URL then fetch its page, attributing failures to the right stage.

    Two stages, reported separately. The previous single-stage version labelled
    every failure ``t.co did not resolve`` even when the shortener had resolved
    perfectly and it was the *destination* that was dead, slow, or rejecting our
    user agent — 163 of 165 errors carried that one misleading label.

    ``resolved_url`` is recorded even when the content fetch fails: knowing an
    account points at ``mattslinks.xyz`` is evidence, whether or not it responds.
    """
    target, html, hops = source_url, None, 0
    try:
        target, html = _get(source_url, timeout)
    except Exception as exc:  # noqa: BLE001
        return {"resolved_url": source_url}, f"resolve: {type(exc).__name__}: {exc}"[:190]

    # Follow client-side interstitials (t.co and friends) up to a small depth.
    while hops < 3 and (nxt := redirect_target(html, base=target)):
        if safe_host(nxt) == safe_host(target) and nxt == target:
            break
        hops += 1
        try:
            target, html = _get(nxt, timeout)
        except Exception as exc:  # noqa: BLE001
            # Destination unreachable, but we DID learn where it points.
            return ({"resolved_url": nxt},
                    f"fetch: {type(exc).__name__}: {exc}"[:190])

    return derive(html, target), None


def derive(html: str, final: str) -> dict:
    """Turn raw HTML into the stored columns. Pure — reused by --reclassify."""
    features = extract(html, final)
    verdict = classify(features)
    return {
        "resolved_url": final,
        "site_type": verdict.site_type,
        "confidence": verdict.confidence,
        "person_signal": verdict.person_signal,
        "is_reviewable": int(verdict.is_reviewable),
        "title": features.title,
        "description": features.description,
        "og_image": features.og_image,
        "images_json": json.dumps(list(features.images)),
        "signal_links_json": json.dumps(list(features.signal_links)),
        "paths_json": json.dumps(list(features.internal_paths)),
        "reasons_json": json.dumps(list(verdict.reasons)),
        "text_excerpt": features.text[:1200],
        "html_gz": gzip.compress(html[:HTML_CAP].encode("utf-8", "replace"), 6),
        "html_bytes": len(html),
        "derived_at": datetime.now(timezone.utc).isoformat(),
    }


def store(conn, account_id: str, username: str, source: str,
          payload: dict, error: str | None) -> None:
    row = {
        "account_id": account_id, "username": username, "source_url": source,
        "resolved_url": None, "site_type": None, "confidence": None,
        "person_signal": None, "is_reviewable": 0, "title": None,
        "description": None, "og_image": None, "images_json": None,
        "signal_links_json": None, "paths_json": None, "reasons_json": None,
        "text_excerpt": None, "error": error,
        "html_gz": None, "html_bytes": None, "derived_at": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    row.update(payload)
    cols = ", ".join(row)
    conn.execute(
        f"INSERT OR REPLACE INTO bio_link_profile ({cols}) "
        f"VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
    conn.commit()


def reclassify(conn) -> int:
    """Re-derive every stored row from its cached HTML. No network at all.

    This is why the raw HTML is kept: the classifier is heuristic and will be
    tuned repeatedly. Iterating on it must never mean re-fetching real people's
    servers.
    """
    rows = conn.execute(
        "SELECT account_id, source_url, resolved_url, html_gz FROM bio_link_profile "
        "WHERE html_gz IS NOT NULL").fetchall()
    if not rows:
        print("✗ no cached HTML — run a fetch pass first")
        return 0
    before = Counter(r["site_type"] for r in
                     conn.execute("SELECT site_type FROM bio_link_profile"))
    for row in rows:
        html = gzip.decompress(row["html_gz"]).decode("utf-8", "replace")
        payload = derive(html, row["resolved_url"] or "")
        payload.pop("html_gz")  # unchanged; avoid rewriting the blob
        sets = ", ".join(f"{k} = ?" for k in payload)
        conn.execute(
            f"UPDATE bio_link_profile SET {sets} "
            f"WHERE account_id = ? AND source_url = ?",
            (*payload.values(), row["account_id"], row["source_url"]))
    conn.commit()
    after = Counter(r["site_type"] for r in
                    conn.execute("SELECT site_type FROM bio_link_profile"))
    print(f"✓ re-derived {len(rows)} rows from cache (no network)\n")
    moved = {k: after.get(k, 0) - before.get(k, 0)
             for k in set(before) | set(after) if after.get(k, 0) != before.get(k, 0)}
    if moved:
        print("Classification drift vs previous rules:")
        for k, d in sorted(moved.items(), key=lambda kv: -abs(kv[1])):
            print(f"  {k or 'unknown':<12} {d:+d}")
    else:
        print("No classification changed.")
    return len(rows)


def report(conn) -> None:
    rows = conn.execute("SELECT * FROM bio_link_profile").fetchall()
    if not rows:
        print("✗ nothing resolved yet — run without --report first")
        return
    ok = [r for r in rows if not r["error"]]
    types = Counter(r["site_type"] for r in ok)
    reviewable = [r for r in ok if r["is_reviewable"]]
    with_signals = [r for r in ok if json.loads(r["signal_links_json"] or "[]")]

    print(f"\n{'=' * 66}\nBIO-LINK RESOLUTION REPORT\n{'=' * 66}")
    print(f"{'✓' if ok else '✗'} resolved            {len(ok)}/{len(rows)}")
    print(f"{'✓' if reviewable else '✗'} worth a human look  {len(reviewable)}")
    print(f"{'✓' if with_signals else '✗'} expose identity links {len(with_signals)}")
    print(f"\nSite types:")
    for t, n in types.most_common():
        bar = "█" * min(30, n)
        print(f"  {t or 'unknown':<12} {n:>4}  {bar}")

    hosts = Counter()
    for r in ok:
        for link in json.loads(r["signal_links_json"] or "[]"):
            parts = link.split("/")
            if len(parts) > 2:
                hosts[parts[2].replace("www.", "")] += 1
    if hosts:
        print(f"\nOff-platform destinations (evidence the follow graph cannot see):")
        for h, n in hosts.most_common(12):
            print(f"  {h:<28} {n:>4}")

    print(f"\nMost person-like pages:")
    for r in sorted(reviewable, key=lambda r: -(r["person_signal"] or 0))[:12]:
        print(f"  @{r['username']:<20} {r['site_type']:<11} "
              f"person={r['person_signal']:.2f}  {(r['title'] or '')[:44]}")

    if any(r["error"] for r in rows):
        errs = Counter(r["error"].split(":")[0] for r in rows if r["error"])
        print(f"\nFailures:")
        for e, n in errs.most_common(8):
            print(f"  {e:<40} {n:>4}")

    print(f"\nNext: review the reviewable pages, then feed their text to the "
          f"existing ensemble prompt for bits.\n{'=' * 66}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="only probe N accounts")
    ap.add_argument("--url", help="probe one URL directly, store nothing")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between fetches")
    ap.add_argument("--refetch", action="store_true", help="re-probe already-stored rows")
    ap.add_argument("--report", action="store_true", help="print report, no network")
    ap.add_argument("--reclassify", action="store_true",
                    help="re-derive all rows from cached HTML, no network")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    if args.url:
        payload, err = probe(args.url)
        if err:
            print(f"✗ {args.url}\n  {err}")
            return 1
        print(f"✓ {args.url}\n  → {payload['resolved_url']}")
        print(f"  type       {payload['site_type']} "
              f"(confidence {payload['confidence']}, person {payload['person_signal']})")
        print(f"  title      {payload['title']}")
        print(f"  descr      {payload['description']}")
        for r in json.loads(payload["reasons_json"]):
            print(f"    · {r}")
        links = json.loads(payload["signal_links_json"])
        if links:
            print(f"  identity links ({len(links)}):")
            for link in links[:12]:
                print(f"    → {link}")
        imgs = json.loads(payload["images_json"])
        print(f"  images     {len(imgs)}")
        for i in imgs[:5]:
            print(f"    ▢ {i}")
        print(f"  text       {payload['text_excerpt'][:400]}...")
        return 0

    conn = connect(args.db)
    if args.reclassify:
        reclassify(conn)
        report(conn)
        return 0
    if args.report:
        report(conn)
        return 0

    targets = pending(conn, args.limit, args.refetch)
    if not targets:
        print("✓ nothing pending — everything with a website is already resolved")
        report(conn)
        return 0

    print(f"Probing {len(targets)} bio links at {args.delay}s intervals "
          f"(~{len(targets) * args.delay / 60:.1f} min)...\n")
    for i, (account_id, username, url) in enumerate(targets, 1):
        payload, err = probe(url)
        store(conn, account_id, username, url, payload, err)
        mark = "✗" if err else "✓"
        detail = err if err else (
            f"{payload['site_type']:<11} person={payload['person_signal']:.2f} "
            f"{(payload['title'] or '')[:40]}")
        print(f"  {mark} [{i:>4}/{len(targets)}] @{(username or '?'):<20} {detail}")
        if i < len(targets):
            time.sleep(args.delay)

    report(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
