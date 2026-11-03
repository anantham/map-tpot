"""Prevent new/changed private research artifacts entering public Git.

Only names in Git's index/diff are inspected; artifact contents and personal
records are never opened. Historical files require a separately approved cleanup.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath

SAFE_DATA_FILES = {"data/.gitkeep", "data/fixtures/.gitkeep", "data/golden/taxonomy.yaml"}
REPOSITORY_FILES = {".gitignore", "AGENTS.md", "CLAUDE.md", "README.md", "update_veil_cv.py"}
PROJECT_FILES = {
    ".dockerignore", ".env.example", ".gitignore", ".nvmrc", ".python-version",
    "Dockerfile", "Makefile", "README.md", "StartGraphExplorer.command", "fly.toml",
    "pytest.ini", "requirements.txt", "requirements-gpu.txt", "requirements-performance.txt",
    "logs/.gitkeep",
}
CONFIG_FILES = {f"config/{name}.json" for name in (
    "community_descriptions", "community_glossary", "community_iconography",
    "enrichment_policy", "graph_settings", "public_site", "publication_fields",
)}
FRONTEND_FILES = {f"{site}/{name}" for site in ("public-site", "graph-explorer")
                  for name in (".env.example", ".gitignore", "README.md", "index.html",
                               "package.json", "package-lock.json", "vite.config.js",
                               "eslint.config.js", "playwright.config.ts", "vercel.json")}
SOURCE_LOCATIONS = {
    "src/": {".py"}, "scripts/": {".py", ".sh"}, "tests/": {".py"},
    "public-site/src/": {".js", ".jsx", ".ts", ".tsx", ".css", ".svg"},
    "public-site/api/": {".js", ".cjs", ".mjs"},
    "public-site/scripts/": {".js", ".cjs", ".mjs"},
    "public-site/__tests__/": {".js", ".jsx", ".ts", ".tsx", ".cjs", ".mjs"},
    "graph-explorer/src/": {".js", ".jsx", ".ts", ".tsx", ".css", ".svg"},
    "graph-explorer/scripts/": {".js", ".cjs", ".mjs"},
    "graph-explorer/e2e/": {".js", ".ts"},
}
DOCUMENT_LOCATIONS = {"docs"} | {f"docs/{directory}" for directory in (
    "adr", "archive", "diagnostics", "experiments", "guides", "modules", "plans",
    "product", "proofs", "reference", "specs", "superpowers", "tasks", "test-plans", "ui",
)}


def publication_path_allowed(path: str) -> bool:
    parsed = PurePosixPath(path)
    if (not path or parsed.is_absolute() or str(parsed) != path or "\\" in path
            or any(ord(character) < 32 for character in path) or ".." in parsed.parts):
        return False
    if path in REPOSITORY_FILES:
        return True
    if path.startswith(".github/workflows/"):
        return len(parsed.parts) == 3 and parsed.suffix in {".yml", ".yaml"}
    if not path.startswith("tpot-analyzer/"):
        return False
    normalized = path.removeprefix("tpot-analyzer/")
    project_path = PurePosixPath(normalized)
    if any(part.lower() in {"secrets", "private", "dossiers", "exports", ".env"}
           for part in project_path.parts):
        return False
    if normalized in SAFE_DATA_FILES | PROJECT_FILES | CONFIG_FILES | FRONTEND_FILES:
        return True
    if project_path.suffix == ".md" and str(project_path.parent) in DOCUMENT_LOCATIONS:
        return True
    if project_path.suffix == ".md" and any(normalized.startswith(directory + "/")
                                            for directory in DOCUMENT_LOCATIONS - {"docs"}):
        return True
    return any(normalized.startswith(directory) and project_path.suffix in extensions
               for directory, extensions in SOURCE_LOCATIONS.items())


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
