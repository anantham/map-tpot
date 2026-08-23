#!/usr/bin/env python3
"""Human-readable smoke check for the exact-tag follow frontier."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

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


def main() -> int:
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
