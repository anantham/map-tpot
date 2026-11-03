#!/usr/bin/env python3
"""Private, offline custody/pilot report. No application imports or migrations.

Read every SQLite input in mode=ro. Joins use exact source account IDs only.
The output is a read view, not a person identity registry or eligibility decision.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path


TABLES = {
    "archive": ("profiles", "tweets", "likes", "retweets", "account_following",
                "account_followers", "enriched_tweets", "user_profile_cache",
                "bio_link_profile", "api_typed_edges", "quote_graph", "mention_graph"),
    "shadow": ("shadow_account", "shadow_edge"),
    "tags": ("account_tags", "account_tag_events", "tag_meta_notes",
             "account_tag_estimate_events"),
}


def readonly(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("source is not a nonempty file")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params)]


def file_identity(path):
    stat = Path(path).stat()
    return {"path": str(Path(path).resolve()), "bytes": stat.st_size,
            "modifiedNs": stat.st_mtime_ns, "device": stat.st_dev, "inode": stat.st_ino}


def tag_digest(conn):
    payload = {}
    for table in TABLES["tags"]:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (table,)).fetchone()
        if exists:
            values = rows(conn, f'SELECT * FROM "{table}"')
            payload[table] = sorted(values, key=lambda row: json.dumps(row, sort_keys=True))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_file(path, kind):
    identity = file_identity(path)
    content = Path(path).read_bytes()
    identity.update(sha256=hashlib.sha256(content).hexdigest(), status="available", kind=kind)
    if kind == "tracker":
        records = list(csv.DictReader(content.decode("utf-8-sig").splitlines(keepends=True)))
    else:
        records = json.loads(content)
    return records, identity


def build_report(*, archive, shadow, tags, captures, research, pilot_size=20):
    """Return a derived report. Missing sources are explicit; errors are not zeros."""
    sources, connections = {}, {}
    with ExitStack() as stack:
        for name, path in (("archive", archive), ("shadow", shadow), ("tags", tags)):
            try:
                conn = readonly(path)
                stack.callback(conn.close)
                connections[name] = conn
                schema = rows(conn, "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
                present = {row["name"] for row in schema}
                counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                          for table in TABLES[name] if table in present}
                sources[name] = {**file_identity(path), "status": "available", "tables": counts,
                                 "missingTables": sorted(set(TABLES[name]) - present), "schema": schema}
                if name == "tags":
                    sources[name]["logicalDigest"] = tag_digest(conn)
            except (OSError, ValueError, sqlite3.Error) as exc:
                sources[name] = {"path": str(path), "status": "unavailable", "errorType": type(exc).__name__}
                connections.pop(name, None)

        def select(source, table, clause="", params=()):
            if table not in sources[source].get("tables", {}):
                return []
            return rows(connections[source], f'SELECT * FROM "{table}" {clause}', params)

        capture_rows, tracker_rows, artifacts, contacts, checks = [], [], {}, {}, {}
        file_errors = []
        for kind, path in (("captures", captures), ("tracker", Path(research) / "outreach-master.csv")):
            try:
                values, identity = read_file(path, kind)
                if not isinstance(values, list) or any(not isinstance(row, dict) or not isinstance(row.get("account_id"), str) or not row["account_id"] for row in values):
                    raise ValueError("records require nonempty string account_id")
                ids = [row["account_id"] for row in values]
                if len(ids) != len(set(ids)):
                    raise ValueError("duplicate source account_id")
                sources[kind] = {**identity, "rows": len(values)}
                if kind == "captures":
                    capture_rows = values
                else:
                    tracker_rows = values
            except (OSError, ValueError) as exc:
                sources[kind] = {"path": str(path), "status": "unavailable", "errorType": type(exc).__name__}

        for pattern, field, destination in (("batch-*.json", "cards", artifacts),
                                             ("contact-route-reviews-*-batch*.json", "reviews", contacts)):
            for path in sorted(Path(research).glob(pattern)):
                try:
                    payload, identity = read_file(path, "research")
                    records = payload[field]
                    if not isinstance(records, list) or any(not isinstance(row, dict) or not isinstance(row.get("account_id"), str) or not row["account_id"] for row in records):
                        raise ValueError("invalid account-bound research records")
                    sources[str(path.resolve())] = {**identity, "rows": len(records)}
                    for record in records:
                        destination.setdefault(record["account_id"], []).append({"sourcePath": str(path.resolve()), "record": record})
                    if destination is contacts:
                        for record in payload.get("checks", []):
                            if not isinstance(record, dict) or not isinstance(record.get("account_id"), str):
                                raise ValueError("invalid account-bound contact check")
                            checks.setdefault(record["account_id"], []).append({"sourcePath": str(path.resolve()), "record": record})
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    file_errors.append({"path": str(path.resolve()), "status": "unavailable", "errorType": type(exc).__name__})

        profiles = select("archive", "profiles")
        profile_by_id = {row["account_id"]: row for row in profiles}
        capture_by_id = {row["account_id"]: row for row in capture_rows}
        tracker_by_id = {row["account_id"]: row for row in tracker_rows}
        judgments = select("tags", "account_tags")
        web_rows = select("archive", "bio_link_profile")
        pilot = []

        def take(ids, reason, quota=4):
            count = 0
            for account_id in sorted(set(ids)):
                if len(pilot) >= pilot_size or count >= quota:
                    break
                if any(row["accountId"] == account_id for row in pilot):
                    continue
                pilot.append({"accountId": account_id, "samplingReason": reason})
                count += 1

        take((row["account_id"] for row in judgments), "existing-judgment")
        rich_ids = [row["account_id"] for row in profiles if row.get("bio") and row.get("website")]
        take(rich_ids, "archive-profile-with-website", 3)
        take((row["account_id"] for row in capture_rows if row["account_id"] not in profile_by_id), "capture-without-archive-profile", 3)
        take((row["account_id"] for row in web_rows if any(host in (row.get("signal_links_json") or "") for host in ("linkedin.com", "bsky.app", "mastodon"))), "cross-platform-website-links", 3)
        shadow_pilot = select("shadow", "shadow_account", "WHERE account_id LIKE 'shadow:%' ORDER BY account_id LIMIT 40")
        take((row["account_id"] for row in shadow_pilot), "unresolved-shadow-identity", 3)
        take((account_id for account_id, values in contacts.items() if any(item["record"].get("routes") for item in values)), "existing-typed-contact", 4)
        take(capture_by_id, "capture-backfill", pilot_size)
        take(profile_by_id, "archive-backfill", pilot_size)

        for dossier in pilot:
            account_id = dossier["accountId"]
            variants = []
            for source, table in (("archive", "profiles"), ("archive", "user_profile_cache"), ("shadow", "shadow_account")):
                for row in select(source, table, "WHERE account_id=?", (account_id,)):
                    row = {key: value for key, value in row.items() if key not in ("raw_json", "scrape_stats")}
                    variants.append({"source": source, "table": table, "record": row})
            if account_id in capture_by_id:
                variants.append({"source": "captures", "record": capture_by_id[account_id]})
            dossier["profiles"] = variants
            handles = {row["record"].get("username") or row["record"].get("handle") for row in variants}
            aliases = []
            for handle in sorted(value for value in handles if value):
                aliases += select("shadow", "shadow_account", "WHERE username=? COLLATE NOCASE AND account_id<>?", (handle, account_id))
                aliases += select("archive", "profiles", "WHERE username=? COLLATE NOCASE AND account_id<>?", (handle, account_id))
            dossier["unresolvedHandleMatches"] = [{"accountId": row["account_id"], "username": row["username"], "status": "not-merged"} for row in aliases]
            dossier["websiteEvidence"] = [{key: value for key, value in row.items() if key not in ("html_gz", "images_json")}
                                          for row in web_rows if row["account_id"] == account_id]
            dossier["publicWorkResearch"] = [{"sourcePath": item["sourcePath"], "artifact": item["record"].get("artifact"), "sourceUrls": item["record"].get("source_urls", []), "caveats": item["record"].get("caveats", [])}
                                               for item in artifacts.get(account_id, [])]
            dossier["contactResearch"] = contacts.get(account_id, [])
            dossier["contactChecks"] = checks.get(account_id, [])
            tracker = tracker_by_id.get(account_id)
            dossier["legacyContactFields"] = ({key: value for key, value in tracker.items() if key.startswith("contact_") or key in ("linkedin_url", "bluesky_url", "mastodon_url")} if tracker else None)
            dossier["workingJudgments"] = [row for row in judgments if row["account_id"] == account_id]
            dossier["coverage"] = {}
            for table, column in (("tweets", "account_id"), ("enriched_tweets", "account_id"), ("account_following", "account_id"), ("account_followers", "account_id")):
                dossier["coverage"][table] = (connections["archive"].execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}"=?', (account_id,)).fetchone()[0]
                                               if table in sources["archive"].get("tables", {}) else None)
        return {"kind": "map-tpot-custody-pilot", "visibility": "private",
                "createdAt": datetime.now(timezone.utc).isoformat(), "sources": sources,
                "researchErrors": file_errors, "dossiers": pilot,
                "limits": ["Account IDs are not verified people.", "No handle-only merges.",
                           "Coverage zero means no stored rows, not no activity.",
                           "Historical archive custody is not current product/export eligibility.",
                           "No event fit, invitation text or private correspondence is promoted to person facts.",
                           "Database identity uses stat/schema/counts, not a full-file cryptographic digest."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "shadow", "tags", "captures", "research", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--tag-backup", type=Path)
    args = parser.parse_args()
    report = build_report(**{key: value for key, value in vars(args).items() if key not in ("output", "tag_backup")})
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.tag_backup:
        args.tag_backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(args.tag_backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with readonly(args.tags) as source, sqlite3.connect(args.tag_backup) as target:
            target.row_factory = sqlite3.Row
            source.backup(target)
            copied_digest = tag_digest(target)
        report["tagBackup"] = {**file_identity(args.tag_backup), "logicalDigest": copied_digest,
                              "matchesSourceReport": copied_digest == report["sources"]["tags"].get("logicalDigest")}
    with args.output.open("x", encoding="utf-8") as target:
        os.chmod(args.output, 0o600)
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write("\n")
    for source in ("archive", "shadow", "tags", "captures", "tracker"):
        status = report["sources"][source]["status"]
        missing = report["sources"][source].get("missingTables", [])
        print(f"{'✓' if status == 'available' and not missing else '✗'} {source}: {status}; missing tables: {len(missing)}")
    print(f"✓ {len(report['dossiers'])} exact-ID dossiers; {len(report['researchErrors'])} research-file errors")
    print("Next: inspect source parity and eligibility before connecting the private Review UI.")
    healthy = all(report["sources"][key]["status"] == "available" and not report["sources"][key].get("missingTables") for key in ("archive", "shadow", "tags", "captures", "tracker"))
    copied = not args.tag_backup or report["tagBackup"]["matchesSourceReport"]
    return 0 if len(report["dossiers"]) == 20 and not report["researchErrors"] and healthy and copied else 1


if __name__ == "__main__":
    raise SystemExit(main())
