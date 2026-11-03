#!/usr/bin/env python3
"""Human-readable smoke check for the exact-tag follow frontier."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == "__main__":
    try:
        import networkx  # noqa: F401
    except ModuleNotFoundError:
        from scripts.dev_runtime import DevRuntimeError, resolve_dev_runtime

        if os.environ.get("TPOT_FRONTIER_VERIFIER_REEXEC") == "1":
            raise SystemExit("✗ backend dependencies are unavailable")
        try:
            runtime = resolve_dev_runtime(PROJECT_ROOT)
        except DevRuntimeError as exc:
            raise SystemExit(f"✗ runtime inputs: {exc}") from exc
        candidates = [PROJECT_ROOT / ".venv" / "bin" / "python"]
        if runtime.primary_project_root is not None:
            candidates.append(
                runtime.primary_project_root / ".venv" / "bin" / "python"
            )
        interpreter = next((path for path in candidates if path.is_file()), None)
        if interpreter is None:
            raise SystemExit("✗ no project Python environment found")
        child_env = dict(os.environ)
        child_env["TPOT_FRONTIER_VERIFIER_REEXEC"] = "1"
        raise SystemExit(subprocess.run(
            [str(interpreter), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=PROJECT_ROOT,
            env=child_env,
            check=False,
        ).returncode)

from src.graph.target_follow_frontier import build_target_follow_frontier
from src.graph.source_selectivity import rank_follow_candidates
from src.data.account_tag_queries import load_target_tag_anchors
from src.data.follow_frontier_archive import (
    load_claimed_following_counts, load_follow_edges, open_archive_readonly,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root: Path) -> tuple[Path, Path]:
    archive = root / "archive.db"
    tags = root / "tags.db"
    with sqlite3.connect(archive) as conn:
        conn.executescript(
            """
            CREATE TABLE account_following (
              account_id TEXT, following_account_id TEXT,
              PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE profiles (account_id TEXT PRIMARY KEY, username TEXT);
            CREATE TABLE user_profile_cache (
              account_id TEXT PRIMARY KEY, username TEXT, following INTEGER
            );
            INSERT INTO account_following VALUES ('selective', 'niche');
            INSERT INTO account_following VALUES ('selective', 'shared');
            INSERT INTO account_following VALUES ('broad', 'shared');
            INSERT INTO account_following VALUES ('negative', 'shared');
            INSERT INTO account_following VALUES ('other', 'wrong-target');
            INSERT INTO profiles VALUES ('niche', 'Niche');
            INSERT INTO profiles VALUES ('shared', 'Shared');
            INSERT INTO user_profile_cache VALUES ('selective', 'S', 2);
            INSERT INTO user_profile_cache VALUES ('broad', 'B', 100);
            INSERT INTO user_profile_cache VALUES ('negative', 'N', 2);
            """
        )
    with sqlite3.connect(tags) as conn:
        conn.executescript(
            """
            CREATE TABLE account_tags (
              ego TEXT, account_id TEXT, tag_key TEXT,
              tag_display TEXT, polarity INTEGER
            );
            INSERT INTO account_tags VALUES ('ego','selective','dharma','Dharma',1);
            INSERT INTO account_tags VALUES ('ego','broad','dharma','Dharma',1);
            INSERT INTO account_tags VALUES ('ego','negative','dharma','Dharma',-1);
            INSERT INTO account_tags VALUES ('ego','other','other','Other',1);
            """
        )
    return archive, tags


def verify_recovery(args: argparse.Namespace) -> int:
    """Development-only LOO; no novel-discovery claims or source writes."""
    started = time.monotonic()
    print("✓ Read-only known-member recovery; existing judgments are development data")
    print("rules: complete positive-reachable pool; remaining anchors excluded; "
          "score descending then account-ID string; misses = N+1 / 100%")
    print("identity: tag_db_sha256=" + _sha256(args.tag_db))
    with closing(open_archive_readonly(args.archive_db)) as conn:
        for tag in args.tag:
            anchors = load_target_tag_anchors(args.tag_db, ego=args.ego, tag=tag)
            positive, negative = set(anchors.positive), set(anchors.negative)
            if len(positive) < 2:
                print(f"✗ {tag}: at least two IN examples required; found {len(positive)}")
                return 1
            edges = load_follow_edges(conn, positive | negative)
            claims = load_claimed_following_counts(conn, positive | negative)
            opposing = {row.account_id: row.selectivity_score for row in
                        rank_follow_candidates(negative, edges, claims).candidates}
            observations = {mode: [] for mode in ("raw_support", "selectivity")}
            sizes = []
            for held_out in sorted(positive):
                training = positive - {held_out}
                rows = [row for row in rank_follow_candidates(training, edges, claims).candidates
                        if row.account_id not in training | negative]
                sizes.append(len(rows))
                scores = {
                    "raw_support": lambda row: row.raw_support,
                    "selectivity": lambda row: row.selectivity_score - opposing.get(row.account_id, 0),
                }
                for mode, score in scores.items():
                    ordered = sorted(rows, key=lambda row: (-score(row), row.account_id))
                    rank = next((i + 1 for i, row in enumerate(ordered)
                                 if row.account_id == held_out), None)
                    observations[mode].append({
                        "recovered": rank is not None,
                        "rank": rank if rank is not None else len(rows) + 1,
                        "percentile": 100 * rank / len(rows) if rank is not None else 100,
                        "top20": rank is not None and rank <= 20,
                    })
            summary = {
                "tag": tag, "positive": len(positive), "negative": len(negative),
                "positiveWithObservedFollows": len({s for s, t in edges if s in positive and s != t}),
                "positiveWithClaimedCounts": len(positive & claims.keys()),
                "candidateRange": [min(sizes), max(sizes)],
                "methods": {mode: {
                    "folds": len(folds), "recovered": sum(r["recovered"] for r in folds),
                    "meanRank": round(mean(r["rank"] for r in folds), 4),
                    "meanPercentile": round(mean(r["percentile"] for r in folds), 5),
                    "top20": sum(r["top20"] for r in folds),
                } for mode, folds in observations.items()},
            }
            print("✓ " + json.dumps(summary, sort_keys=True))
    print(f"✓ Completed in {time.monotonic() - started:.2f}s; no source writes or paid calls")
    print("next: evaluate unfamiliar candidates with the curator; these results do not measure discovery")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-db", type=Path)
    parser.add_argument("--tag-db", type=Path)
    parser.add_argument("--ego")
    parser.add_argument("--tag", action="append")
    args = parser.parse_args()
    if any((args.archive_db, args.tag_db, args.ego, args.tag)):
        if not all((args.archive_db, args.tag_db, args.ego, args.tag)):
            parser.error("recovery requires --archive-db, --tag-db, --ego and --tag")
        return verify_recovery(args)
    with tempfile.TemporaryDirectory(prefix="verify-frontier-") as raw_root:
        archive, tags = _fixture(Path(raw_root))
        before = _sha256(archive)
        payload = build_target_follow_frontier(
            tag_db_path=tags,
            archive_db_path=archive,
            ego="ego",
            tag="Dharma",
            limit=10,
        )
        raw = build_target_follow_frontier(
            tag_db_path=tags, archive_db_path=archive, ego="ego", tag="Dharma",
            limit=1, ranking="raw_support",
        )
        after = _sha256(archive)

    candidates = {row["accountId"]: row for row in payload["candidates"]}
    checks = [
        (payload["anchors"]["positive"]["count"] == 2, "exact tag anchors"),
        ("wrong-target" not in candidates, "unrelated tags remain isolated"),
        (
            candidates["niche"]["contrast"] > candidates["shared"]["contrast"],
            "negative support changes the ordering",
        ),
        (payload["status"] == "provisional", "status remains provisional"),
        (raw["candidates"][0]["accountId"] == "shared", "raw support ranks full pool before limiting"),
        (raw["candidates"][0]["ranks"]["selectivity"] == 2, "alternate rank survives truncation"),
        (before == after, "archive bytes unchanged by read-only ranking"),
    ]
    for passed, label in checks:
        print(f"{'✓' if passed else '✗'} {label}")
    print(
        "metrics: "
        f"anchors=+{payload['anchors']['positive']['count']}"
        f"/-{payload['anchors']['negative']['count']} "
        f"candidates={payload['diagnostics']['candidateCount']} "
        "observed_pair_fraction="
        f"{payload['diagnostics']['observedPositivePairLinks']['observedFraction']}"
    )
    print(
        "next: compare rank movement after durable curator tags; do not "
        "interpret this uncalibrated ordering as a cluster-existence result"
    )
    return 0 if all(passed for passed, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
