"""Prevent new/changed private research artifacts entering public Git.

Only names in Git's index/diff are inspected; artifact contents and personal
records are never opened. Historical files require a separately approved cleanup.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath

SAFE_DATA_FILES = {"data/.gitkeep", "data/fixtures/.gitkeep", "data/golden/taxonomy.yaml"}


def publication_path_allowed(path: str) -> bool:
    normalized = path.removeprefix("tpot-analyzer/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("../") or ".." in parts:
        return False
    if normalized.startswith("data/"):
        return normalized in SAFE_DATA_FILES
    if normalized.startswith(("secrets/", "Related data/", "docs/private/", "docs/dossiers/")):
        return False
    if normalized in {"public-site/public/data.json", "public-site/public/search.json",
                      "public-site/public/publication-manifest.json", "graph-explorer/public/analysis_output.json"}:
        return False
    if any(part in {"secrets", "dossiers", ".env"} for part in parts):
        return False
    if PurePosixPath(normalized).suffix.lower() in {".pkl", ".pickle", ".db", ".sqlite", ".sqlite3"}:
        return False
    return True


def changed_paths(*, base: str | None = None) -> list[str]:
    args = ["git", "diff", "--name-only", "-z", "--diff-filter=ACMR"]
    if base is not None:
        if not base or set(base) == {"0"}:
            raise ValueError("CI baseline must be a real commit; zero/missing explicit base cannot use staged mode")
        subprocess.run(["git", "rev-parse", "--verify", f"{base}^{{commit}}"], check=True, capture_output=True)
        args += [base, "HEAD", "--"]
    else:
        args += ["--cached", "--"]
    output = subprocess.check_output(args)
    return [path.decode("utf-8") for path in output.split(b"\0") if path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Compare base commit to HEAD; defaults to staged paths")
    args = parser.parse_args()
    try:
        paths = changed_paths(base=args.base)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"✗ Public-Git publication boundary: invalid baseline ({exc})")
        print("Next: supply an approved base commit or a fetched default-branch reference.")
        return 1
    rejected = [path for path in paths if not publication_path_allowed(path)]
    if rejected:
        print(f"✗ Public-Git publication boundary: {len(rejected)} prohibited artifact paths among {len(paths)} changed paths")
        for path in rejected:
            print(f"  blocked path: {path}")
        print("Next: keep private artifacts local; explicit owner review is required for policy changes or historical cleanup.")
        return 1
    print(f"✓ Public-Git publication boundary: {len(paths)} changed paths checked; no private artifact additions or edits")
    print("Next: review candidate bytes and exact digest before any separately authorized public upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
