"""Migration: Add short_name to community table, migrate account_community_bits to use community_id.

This migration:
1. Adds `short_name` column to `community` table (the labeling handle)
2. Populates short_name for all 14 communities
3. Migrates `account_community_bits` from community_name (string) to community_id (FK)

The short_name is the stable identifier used by the labeling system (bits tags).
The full name (community.name) is the display name that can evolve.
The UUID (community.id) is the true FK that never changes.

Usage:
    .venv/bin/python3 -m scripts.migrate_community_short_names
    .venv/bin/python3 -m scripts.migrate_community_short_names --db-path data/archive_tweets.db
    .venv/bin/python3 -m scripts.migrate_community_short_names --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

DB_PATH = DEFAULT_ARCHIVE_DB

# Mapping: community UUID -> short_name (labeling handle)
# These match the names used in bits tags: bits:LLM-Whisperers:+3
SHORT_NAMES = {
    "1ae87669-1092-4fd8-b25f-1588ab9ce667": "AI-Safety",
    "37d004fc-32fb-471c-a89e-e260cc19318b": "Emergence-Self-Transformation",
    "60d2a359-603d-4880-b59b-ffc17cf12366": "Contemplative-Practitioners",
    "68821476-4076-472b-94be-7c0cab896ccf": "Collective-Intelligence",
    "7dff6a20-f5e1-4c53-bc92-80f5d4ef661a": "Feline-Poetics",
    "86ea371b-c9de-418f-9cf6-21f308c2775a": "NYC-Institution-Builders",
    "8e87c0b1-984c-4327-a0e7-eb7be007a414": "Quiet-Creatives",
    "ad6fb455-8671-4390-a6da-becfaac83459": "Queer-TPOT",
    "bbfe5387-a5f9-41f5-b3f9-80fc83aa4f6e": "LLM-Whisperers",
    "bc944819-8805-4d1f-bcf8-54f3f53c8e2a": "Builders",
    "d1ec7742-480b-41bb-a1dc-21d58e93a265": "Relational-Explorers",
    "e8e6e7d0-bfa6-49c4-96e4-f10942210496": "Ethereum-Builders",
    "effaff86-24d3-425d-a96d-11919f93abdc": "highbies",
    "f5e6154d-fb76-4f1a-af78-ab9aa8838815": "Qualia-Research",
}

# Reverse: short_name -> community_id (for migrating account_community_bits)
SHORT_NAME_TO_ID = {v: k for k, v in SHORT_NAMES.items()}


def migrate(db_path: Path, dry_run: bool = False) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    # --- Step 1: Add short_name column to community ---
    cols = [row[1] for row in conn.execute("PRAGMA table_info(community)").fetchall()]
    if "short_name" not in cols:
        print("Adding short_name column to community table...")
        if not dry_run:
            conn.execute("ALTER TABLE community ADD COLUMN short_name TEXT")
    else:
        print("short_name column already exists.")

    # --- Step 2: Populate short_names ---
    has_short = "short_name" in [
        row[1] for row in conn.execute("PRAGMA table_info(community)").fetchall()
    ]
    if has_short:
        rows = conn.execute("SELECT id, name, short_name FROM community").fetchall()
    else:
        rows = [(r[0], r[1], None) for r in conn.execute("SELECT id, name FROM community").fetchall()]
    updated = 0
    for cid, name, existing_short in rows:
        short = SHORT_NAMES.get(cid)
        if short and existing_short != short:
            print(f"  {name} -> short_name={short}")
            if not dry_run:
                conn.execute(
                    "UPDATE community SET short_name = ? WHERE id = ?",
                    (short, cid),
                )
            updated += 1
        elif not short:
            print(f"  WARNING: No short_name mapping for community '{name}' (id={cid})")
    print(f"Updated {updated} community short_names.")

    # --- Step 3: Migrate account_community_bits ---
    # Check if old table exists with community_name column
    old_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='account_community_bits'"
    ).fetchone()

    if old_table:
        old_cols = [
            row[1]
            for row in conn.execute("PRAGMA table_info(account_community_bits)").fetchall()
        ]

        if "community_name" in old_cols:
            print("\nMigrating account_community_bits: community_name -> community_id...")
            old_rows = conn.execute(
                "SELECT account_id, community_name, total_bits, tweet_count, pct, updated_at "
                "FROM account_community_bits"
            ).fetchall()
            print(f"  Found {len(old_rows)} rows to migrate.")

            if not dry_run:
                conn.execute("DROP TABLE account_community_bits")
                conn.execute("""
                    CREATE TABLE account_community_bits (
                        account_id   TEXT NOT NULL,
                        community_id TEXT NOT NULL,
                        total_bits   INTEGER NOT NULL DEFAULT 0,
                        tweet_count  INTEGER NOT NULL DEFAULT 0,
                        pct          REAL NOT NULL DEFAULT 0.0,
                        updated_at   TEXT NOT NULL,
                        PRIMARY KEY (account_id, community_id),
                        FOREIGN KEY (community_id) REFERENCES community(id)
                    )
                """)

                migrated = 0
                for acct_id, comm_name, bits, tc, pct, updated in old_rows:
                    comm_id = SHORT_NAME_TO_ID.get(comm_name)
                    if comm_id:
                        conn.execute(
                            "INSERT INTO account_community_bits "
                            "(account_id, community_id, total_bits, tweet_count, pct, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (acct_id, comm_id, bits, tc, pct, updated),
                        )
                        migrated += 1
                        print(f"  {comm_name} -> {comm_id[:8]}... ({bits:+d} bits)")
                    else:
                        print(f"  WARNING: No ID mapping for community_name '{comm_name}', skipping")
                print(f"  Migrated {migrated}/{len(old_rows)} rows.")

        elif "community_id" in old_cols:
            print("\naccount_community_bits already uses community_id. No migration needed.")
        else:
            print(f"\nWARNING: account_community_bits has unexpected columns: {old_cols}")
    else:
        print("\naccount_community_bits table doesn't exist yet. Creating with new schema...")
        if not dry_run:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_community_bits (
                    account_id   TEXT NOT NULL,
                    community_id TEXT NOT NULL,
                    total_bits   INTEGER NOT NULL DEFAULT 0,
                    tweet_count  INTEGER NOT NULL DEFAULT 0,
                    pct          REAL NOT NULL DEFAULT 0.0,
                    updated_at   TEXT NOT NULL,
                    PRIMARY KEY (account_id, community_id),
                    FOREIGN KEY (community_id) REFERENCES community(id)
                )
            """)

    if not dry_run:
        conn.commit()
        print("\nMigration committed.")
    else:
        print("\nDRY RUN — no changes made.")

    # --- Verify ---
    print("\n=== Verification ===")
    has_short_now = "short_name" in [
        row[1] for row in conn.execute("PRAGMA table_info(community)").fetchall()
    ]
    if has_short_now:
        rows = conn.execute("SELECT id, name, short_name FROM community ORDER BY name").fetchall()
    else:
        rows = [(r[0], r[1], None) for r in conn.execute("SELECT id, name FROM community ORDER BY name").fetchall()]
    for cid, name, short in rows:
        status = "OK" if short else "MISSING"
        print(f"  [{status}] {name} -> {short or '???'}")

    bits_rows = conn.execute("SELECT * FROM account_community_bits").fetchall()
    print(f"\naccount_community_bits: {len(bits_rows)} rows")
    bits_cols = [row[1] for row in conn.execute("PRAGMA table_info(account_community_bits)").fetchall()]
    print(f"  columns: {bits_cols}")
    for r in bits_rows:
        print(f"  {r}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate community short_names")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"DB not found: {args.db_path}")
        sys.exit(1)

    migrate(args.db_path, dry_run=args.dry_run)
