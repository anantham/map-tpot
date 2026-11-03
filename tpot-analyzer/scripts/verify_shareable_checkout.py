#!/usr/bin/env python3
"""Check the current Git index's data boundary; never read private data contents."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


PUBLIC_DATA_FILES = {
    "tpot-analyzer/data/.gitkeep",
    "tpot-analyzer/data/fixtures/.gitkeep",
    "tpot-analyzer/data/manifests/twitterapiio_price_card_20260730.json",
}
PRIVATE_PROBES = (
    "Related data/new-capture.zip",
    "tpot-analyzer/data/private/example/capture.json",
    "tpot-analyzer/data/new-capture.json",
    "tpot-analyzer/data/new-contacts.csv",
    "tpot-analyzer/data/evals/example.json",
    "tpot-analyzer/data/manifests/new-capture.json",
    "tpot-analyzer/data/fixtures/new-profile.json",
    "tpot-analyzer/data/account_tags.db-wal",
    "tpot-analyzer/data/archive_tweets.db",
    "tpot-analyzer/.env",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path,
                        default=Path(__file__).resolve().parents[2])
    root = parser.parse_args().repo_root.resolve()
    checks = []

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, check=False)

    tracked = git("ls-files", "-z", "--", "tpot-analyzer/data/", "Related data/")
    if tracked.returncode:
        print("✗ Git index unavailable; no data-boundary claim can be made")
        return 1
    paths = {p.decode("utf-8", "surrogateescape")
             for p in tracked.stdout.split(b"\0") if p}
    unexpected = sorted(paths - PUBLIC_DATA_FILES)
    checks.append((not unexpected, "tracked data allowlist",
                   f"{len(paths)} entries, {len(unexpected)} unexpected"))
    for path in unexpected:
        print(f"  excluded-from-release candidate: {path}")

    for path in PRIVATE_PROBES:
        result = git("check-ignore", "--no-index", "-q", "--", path)
        checks.append((result.returncode == 0, "ignore probe", path))
    for path in sorted(PUBLIC_DATA_FILES):
        result = git("check-ignore", "--no-index", "-q", "--", path)
        checks.append((result.returncode == 1, "explicit public input", path))

    for passed, label, detail in checks:
        print(f"{'✓' if passed else '✗'} {label}: {detail}")
    passed = sum(item[0] for item in checks)
    print(f"Result: {passed}/{len(checks)} checks passed")
    print("Scope: index paths and ignore rules only; not a content/secret audit,")
    print("history purge, data backup, remote verification or publishing approval.")
    if passed != len(checks):
        print("Next: preserve local files; inspect unexpected tracked paths and")
        print("ignore rules. Do not delete data or rewrite history to pass this check.")
        return 1
    print("Next: review code/docs for disclosure, run tests, and inspect the")
    print("exact commit before a separately authorized push. Raw data stays local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
