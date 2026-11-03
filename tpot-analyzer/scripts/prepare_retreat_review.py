#!/usr/bin/env python3
"""Build a private exploratory retreat packet from explicit research leads.

This does not turn curated leads into a ranking benchmark or accepted labels.
Profiles, observed paths and posts are read from local databases in read-only
mode; primary-source work checks and caveats come from the supplied lead file.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_discovery_review import evidence_for  # noqa: E402
from src.data.discovery_review_store import load_review_packet  # noqa: E402


def readonly(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def profile_for(archive, cache, lead):
    table = lead["profile_table"]
    account_id = lead["account_id"]
    if table == "profiles":
        row = archive.execute("SELECT account_id,username,display_name,bio,location,fetched_at "
                              "FROM profiles WHERE account_id=?", (account_id,)).fetchone()
    elif table == "user_profile_cache":
        row = archive.execute("SELECT account_id,username,description AS bio,location,fetched_at "
                              "FROM user_profile_cache WHERE account_id=?", (account_id,)).fetchone()
    elif table == "shadow_account":
        row = cache.execute("SELECT account_id,username,display_name,bio,location,fetched_at "
                            "FROM shadow_account WHERE account_id=?", (account_id,)).fetchone()
    else:
        raise ValueError("Unsupported profile source table")
    if row is None or row["username"].casefold() != lead["username"].casefold():
        raise ValueError("Lead identity does not match its named profile source")
    profile = dict(row)
    profile.setdefault("display_name", lead["display_name"])
    return profile


def observed_connection(archive, cache, lead):
    observations = []
    for edge in lead["observed_follows"]:
        source, target = edge["source_id"], edge["target_id"]
        table = edge["table"]
        if table == "shadow_edge":
            row = cache.execute("SELECT fetched_at FROM shadow_edge WHERE source_id=? "
                                "AND target_id=? AND direction=?", (source, target, edge["direction"])).fetchone()
        elif table == "account_following":
            row = archive.execute("SELECT NULL AS fetched_at FROM account_following "
                                  "WHERE account_id=? AND following_account_id=?", (source, target)).fetchone()
        elif table == "account_followers":
            row = archive.execute("SELECT NULL AS fetched_at FROM account_followers "
                                  "WHERE follower_account_id=? AND account_id=?", (source, target)).fetchone()
        else:
            raise ValueError("Unsupported observed follow source")
        if row is None:
            raise ValueError("A supplied seed-to-candidate path is not stored")
        date = row["fetched_at"] or "unknown date (archive edge has no capture timestamp)"
        observations.append(f"@{edge['seed_username']} follows @{lead['username']}; "
                            f"stored in {table}, captured {date}.")
    return " ".join(observations) + " An observed follow is not an endorsement or introduction."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("leads", "archive-db", "cache-db", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / "data/private").resolve()):
        raise ValueError("Output must be in this checkout's ignored data/private")
    manifest_path = output / "manifest.json"
    if output.exists():
        raise ValueError("Refusing to overwrite an existing retreat packet directory")
    if subprocess.run(["git", "check-ignore", "-q", str(manifest_path)], cwd=ROOT).returncode:
        raise ValueError("Retreat evidence must remain gitignored")
    raw = args.leads.read_bytes()
    leads = json.loads(raw)
    cards, order = {}, []
    with closing(readonly(args.archive_db)) as archive, closing(readonly(args.cache_db)) as cache:
        for lead in leads["candidates"]:
            account_id, username = lead["account_id"], lead["username"]
            if account_id in cards:
                raise ValueError("Duplicate lead identity")
            card = evidence_for(archive, account_id, username)
            card["profile"] = profile_for(archive, cache, lead)
            card["discovery"] = {
                "contribution_hypothesis": lead["fit_hypothesis"],
                "connection": observed_connection(archive, cache, lead),
                "location_evidence": lead["location_evidence"],
                "work": lead["verified_work"],
                "unknowns": leads["common_unknowns"] + lead.get("specific_unknowns", []),
            }
            cards[account_id] = card
            order.append(account_id)
        if archive.total_changes or cache.total_changes:
            raise ValueError("Unexpected source write")
    manifest = {
        "schema_version": 1, "kind": "exploratory_retreat_review", "status": "unjudged",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": leads["purpose"], "freeze": {"ego": leads["curator"]},
        "review_order": order, "evidence": cards,
        "research_source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_archive": str(args.archive_db.resolve()), "source_cache": str(args.cache_db.resolve()),
        "screening_counts": leads["screening_counts"],
        "selection_policy": "Human-readable research triage of stored follow neighborhoods. "
            "Priority order is exploratory, not method-masked or a fair ranking comparison.",
        "limitations": leads["limitations"],
    }
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True)
    descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
    packet = load_review_packet(manifest_path)
    print(f"✓ Separate purpose: {packet.purpose['title']}; no prefilled answers")
    print(f"✓ {len(order)} profiles and observed seed paths verified against read-only sources")
    print(f"✓ Public work cards: {sum(bool(c['discovery']['work']) for c in packet.cards)}; "
          f"stored posts: {sum(len(c['posts']) for c in packet.cards)}")
    print(f"✓ Private packet created without overwrite: {manifest_path}")
    print(f"Packet SHA256: {packet.packet_id}")
    print("Next: run verify_discovery_review.py --packet <manifest>; review personal usefulness.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, sqlite3.Error) as exc:
        print(f"✗ Retreat packet preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
