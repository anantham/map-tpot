#!/usr/bin/env python3
"""Prepare one private, unjudged discovery packet from read-only local evidence."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from src.data.follow_frontier_archive import (  # noqa: E402
    load_claimed_following_counts, load_follow_edges, load_usernames,
    open_archive_readonly,
)
from src.graph.source_selectivity import rank_follow_candidates  # noqa: E402

K, SHUFFLE_SEED = 10, 20260922


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def safe_text(value):
    text = html.escape(str(value or ""), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", text)


def require_columns(conn, table, required):
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if not set(required.split()) <= columns:
        raise ValueError(f"Required local evidence schema is missing in {table}")


def rank_methods(conn, freeze, excluded):
    positive, negative = map(set, (freeze["extension"]["in"], freeze["extension"]["not_in"]))
    anchors = positive | negative
    if len(positive) != 8 or len(negative) != 4 or positive & negative:
        raise ValueError("This formative packet requires the frozen 8/4 Dharma extension")
    edges = load_follow_edges(conn, anchors)
    claims = load_claimed_following_counts(conn, anchors)
    pos = rank_follow_candidates(positive, edges, claims)
    neg = {row.account_id: row for row in rank_follow_candidates(negative, edges, claims).candidates}
    rows = []
    for row in pos.candidates:
        if row.account_id in excluded | anchors:
            continue
        against = neg.get(row.account_id)
        minus = against.selectivity_score if against else 0.0
        rows.append({"account_id": row.account_id, "raw_support": row.raw_support,
                     "positive_score": row.selectivity_score, "negative_score": minus,
                     "contrast": row.selectivity_score - minus})
    raw = sorted(rows, key=lambda r: (-r["raw_support"], r["account_id"]))
    contrast = sorted(rows, key=lambda r: (-r["contrast"], -r["positive_score"],
                                          r["negative_score"], r["account_id"]))
    placeholders = ",".join("?" for _ in positive)
    incoming = sorted(tuple(map(str, row)) for row in conn.execute(
        f"SELECT account_id,follower_account_id FROM account_followers "
        f"WHERE account_id IN ({placeholders})", sorted(positive)))
    supporters = defaultdict(set)
    for anchor, candidate in incoming:
        if candidate != anchor and candidate not in excluded | anchors:
            supporters[candidate].add(anchor)
    reverse = sorted(({"account_id": aid, "raw_support": len(seeds)}
                      for aid, seeds in supporters.items()),
                     key=lambda r: (-r["raw_support"], r["account_id"]))
    methods = {"outgoing_raw": raw, "outgoing_selectivity_contrast": contrast,
               "incoming_raw": reverse}
    selected = {name: [dict(row, rank=i + 1) for i, row in enumerate(order[:K])]
                for name, order in methods.items()}
    return selected, {
        "eligible_pool_sizes": {name: len(order) for name, order in methods.items()},
        "outgoing_edges_sha256": digest(sorted(edges)),
        "incoming_edges_sha256": digest(incoming), "claimed_degrees": claims,
        "positive_source_diagnostics": [vars(row) for row in pos.seed_diagnostics],
        "negative_source_diagnostics": [vars(row) for row in
            rank_follow_candidates(negative, edges, claims).seed_diagnostics],
        "outgoing_edge_count": len(edges), "incoming_edge_count": len(incoming),
    }


def evidence_for(conn, account_id, username):
    profile = conn.execute("SELECT account_id,username,display_name,bio,location,"
                           "fetched_at FROM profiles WHERE account_id=?", (account_id,)).fetchone()
    posts, availability = {}, {}
    for table, text_column in (("tweets", "full_text"), ("enriched_tweets", "text")):
        availability[table] = bool(conn.execute(
            f"SELECT 1 FROM {table} WHERE account_id=? LIMIT 1", (account_id,)).fetchone())
        query = (f"SELECT tweet_id,created_at,{text_column} AS text,fetched_at FROM {table} "
                 f"WHERE account_id=? AND trim({text_column}) != '' "
                 f"AND ltrim({text_column}) NOT LIKE 'RT @%' "
                 "ORDER BY CAST(tweet_id AS INTEGER) DESC LIMIT 3")
        for row in conn.execute(query, (account_id,)):
            tweet = dict(row)
            if not str(tweet["tweet_id"]).isdigit():
                raise ValueError("Post identifier is not a canonical numeric tweet ID")
            tweet["source"] = table
            tweet["url"] = f"https://x.com/i/status/{tweet['tweet_id']}"
            posts.setdefault(tweet["tweet_id"], tweet)
    chosen = sorted(posts.values(), key=lambda p: int(p["tweet_id"]), reverse=True)[:3]
    return {"account_id": account_id, "username": username,
            "profile": dict(profile) if profile else None,
            "availability": availability, "posts": chosen}


def render_review(order, evidence):
    lines = ["# Private discovery review — unjudged formative packet", "",
             "Read this file before manifest.json, which reveals selection methods. "
             "The item order is shuffled, not a ranking. This does not replace the "
             "older 150-account deck, its preregistration, or the existing Review UI.", "",
             "Judge relevance to Dharma as you use the term, whether you already knew "
             "the account, and whether you are glad to have it surfaced. Missing evidence "
             "is not a negative judgment; use ABSTAIN or UNSURE where appropriate. "
             "Nothing here has been judged, and this file writes no accepted tags.", "",
             "All three answers describe your current view, not objective membership truth. "
             "Fixed scoring rule: confirmed useful-new means relevance IN AND known NO "
             "AND glad YES. After judging, report the count out of each method's ten "
             "alongside unresolved/abstained counts; this is not calibrated precision. "
             "Do not turn missing evidence or abstention into OUT.", "",
             "You may stop after the first ten shuffled items as a usability pilot. "
             "Do not compare method winners before all items are judged unless the "
             "comparison is explicitly marked partial.", "",
             "Fixed evidence policy: local profile plus up to three most recent nonempty, "
             "non-retweet posts across authored/enriched tables, deduplicated by tweet ID; "
             "archive text wins duplicate IDs. Recency uses descending numeric tweet ID; "
             "stored dates are shown verbatim and may be missing or inconsistent. "
             "No evidence-based candidate replacement or live fetching.", ""]
    for index, aid in enumerate(order, 1):
        card = evidence[aid]
        identity = "@" + card["username"] if card["username"] else "unresolved handle"
        profile = card["profile"] or {}
        lines += [f"## Item {index:02d} — {safe_text(identity)}", "",
                  f"Canonical account ID: {aid}", ""]
        if card["username"] and re.fullmatch(r"[A-Za-z0-9_]{1,15}", card["username"]):
            lines += [f"[Open profile](https://x.com/{card['username']})", ""]
        else:
            lines += ["Profile link: unavailable (handle missing or invalid).", ""]
        lines += [
                  f"Profile: {'available' if profile else 'missing locally'}",
                  f"Display name: {safe_text(profile.get('display_name')) or 'missing locally'}",
                  f"Bio: {safe_text(profile.get('bio')) or 'missing locally'}",
                  f"Declared location: {safe_text(profile.get('location')) or 'missing locally'}",
                  f"Profile captured: {safe_text(profile.get('fetched_at')) or 'unknown'}", ""]
        for post in card["posts"]:
            lines += [f"Post date: {safe_text(post['created_at']) or 'unknown'}; "
                      f"captured: {safe_text(post['fetched_at']) or 'unknown'}; "
                      f"source: {post['source']}; [original post]({post['url']})", ""]
            lines += ["> " + safe_text(line) for line in post["text"].splitlines()]
            lines.append("")
        if not card["posts"]:
            lines += ["Posts: no eligible local authored/enriched posts available.", ""]
        lines += ["Relevance (IN / OUT / ABSTAIN):", "", "Known (YES / NO / UNSURE):", "",
                  "Glad found (YES / NO / UNSURE):", "", "Notes:", "", "---", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive-db", "tag-db", "freeze", "output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((PROJECT_ROOT / "data/private").resolve()):
        raise ValueError("Output must be inside this checkout's ignored data/private directory")
    if any((output / name).exists() for name in ("manifest.json", "review.md")):
        raise ValueError("Refusing to overwrite an existing manifest or review packet")
    for name in ("manifest.json", "review.md"):
        ignored = subprocess.run(["git", "check-ignore", "-q", str(output / name)], cwd=PROJECT_ROOT)
        if ignored.returncode != 0:
            raise ValueError("Both private output paths must be ignored by git")
    freeze_bytes = args.freeze.read_bytes()
    freeze = json.loads(freeze_bytes)
    with closing(open_archive_readonly(args.archive_db)) as conn, closing(
            open_archive_readonly(args.tag_db)) as tags:
        for table, columns in {"profiles": "account_id username display_name bio location fetched_at",
                               "account_followers": "account_id follower_account_id",
                               "tweets": "account_id tweet_id full_text created_at fetched_at",
                               "enriched_tweets": "account_id tweet_id text created_at fetched_at"}.items():
            require_columns(conn, table, columns)
        require_columns(tags, "account_tags", "ego account_id tag_key polarity")
        tag_rows = [dict(row) for row in tags.execute(
            "SELECT * FROM account_tags WHERE ego=? ORDER BY account_id,tag_key", (freeze["ego"],))]
        excluded = {str(row["account_id"]) for row in tag_rows}
        methods, inputs = rank_methods(conn, freeze, excluded)
        order = sorted({row["account_id"] for rows in methods.values() for row in rows})
        random.Random(SHUFFLE_SEED).shuffle(order)
        handles = load_usernames(conn, order)
        evidence = {aid: evidence_for(conn, aid, handles.get(aid)) for aid in order}
        if conn.total_changes or tags.total_changes:
            raise ValueError("Unexpected source database change")
    review = render_review(order, evidence)
    stats = {"accounts": len(order), "excluded_accounts": len(excluded),
             "profiles": sum(bool(c["profile"]) for c in evidence.values()),
             "handles": sum(bool(c["username"]) for c in evidence.values()),
             "accounts_with_selected_posts": sum(bool(c["posts"]) for c in evidence.values()),
             "selected_posts": sum(len(c["posts"]) for c in evidence.values())}
    method_coverage = {name: {
        "accounts": len(rows),
        "profiles": sum(bool(evidence[r["account_id"]]["profile"]) for r in rows),
        "handles": sum(bool(evidence[r["account_id"]]["username"]) for r in rows),
        "with_selected_posts": sum(bool(evidence[r["account_id"]]["posts"]) for r in rows),
    } for name, rows in methods.items()}
    manifest = {"kind": "formative_discovery_review", "status": "unjudged", "schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(), "k": K,
                "shuffle_seed": SHUFFLE_SEED, "review_order": order, "methods": methods,
                "freeze": freeze, "freeze_file_sha256": hashlib.sha256(freeze_bytes).hexdigest(),
                "source_archive": str(args.archive_db.resolve()), "source_tags": str(args.tag_db.resolve()),
                "source_binding": "read-only mutable database views; relevant inputs logically hashed",
                "tag_rows_sha256": digest(tag_rows), "excluded_account_ids": sorted(excluded),
                "inputs": inputs, "evidence": evidence, "aggregate_counts": stats,
                "method_coverage": method_coverage,
                "method_policy": {
                    "outgoing_raw": "Positive-anchor distinct follows; descending support then canonical ID",
                    "outgoing_selectivity_contrast": "Positive minus negative reciprocal effective-degree support; "
                        "descending contrast, descending positive score, ascending negative score, canonical ID",
                    "incoming_raw": "Distinct positive anchors in account_followers; descending count then canonical ID",
                    "effective_degree": "max(observed non-self unique outgoing degree, valid claimed following count)",
                    "exclusions": "All current account_tags subjects for frozen ego, plus frozen anchors, before top K",
                    "judgment_rule": "useful-new iff relevance=IN AND known=NO AND glad=YES; "
                        "report count/10 and unresolved/abstained count; no missing-to-OUT conversion",
                    "completion": "All three answers express current curator view; first 10 may be usability pilot; "
                        "method comparisons before all 28 judgments must be explicitly partial",
                },
                "evidence_sha256": digest(evidence),
                "review_sha256": hashlib.sha256(review.encode()).hexdigest(),
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limitations": ["Not a sealed benchmark; no human judgments inferred",
                    "Known status requires human response, not follow/tag proxies",
                    "Methods have unequal evidence coverage and candidate universes",
                    "Contrast versus raw changes weighting and negative use",
                    "No historical fame penalty; incoming uses account_followers only"]}
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, text in (("manifest.json", json.dumps(manifest, indent=2) + "\n"), ("review.md", review)):
        descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)
    print("✓ Source databases opened read-only/query-only; source writes: 0")
    print("✓ Frozen anchors used; already-tagged accounts excluded before top 10")
    print("✓ Separate ignored private files created without overwriting; permissions 0600")
    print("✓ Review shuffled with fixed seed; no method scores or prefilled judgments")
    print("metrics: " + json.dumps(stats, sort_keys=True))
    print("next: review the packet before opening its method manifest; record only human judgments")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, sqlite3.DatabaseError) as exc:
        print(f"✗ Discovery packet preparation stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
