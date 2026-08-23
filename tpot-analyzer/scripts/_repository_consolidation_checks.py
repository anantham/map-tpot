"""Read-only checks for the 2026-08-23 repository consolidation gate."""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


BASE_MAIN = "7cfb45fc6cf84115fdd9968064a962751983a55b"
SNAPSHOT = "bf2e61fca89c4762387964db30a933bfd5004808"
STASH = "21e50c0035cfd0d7d0be72bbf3c58627587400ff"
RAW_STATUS_SHA256 = (
    "1d39f0b49df4695f467997c2633af7cca5b14e8e3af1fd32333ffb23865e5c88"
)
BUNDLE_SHA256 = "f3ac9c2543ea403f90ae71176da2b99c4878c48da4c0fba7a3a34d9b7667a86b"
PRESERVED_REFS = {
    "codex/preserve/community-archive-readiness-20260823":
        "00214b475aa66437b13cde10b7eedb27aa01a1b8",
    "codex/preserve/local-first-discovery-docs-20260823":
        "bb9a29e439163e1f24c88b9a9d17bfc902abfcca",
    "codex/preserve/personal-ontology-slice-1-20260823":
        "d1cd76be2829085c5d540c159f97f8edd219a888",
    "codex/preserve/raw-first-retrieval-committed-20260823":
        "81d844d939716c407eaad1efa62cb40925419772",
    "codex/preserve/raw-first-worktree-20260823": SNAPSHOT,
    "codex/preserve/dossier-stash-20260823": STASH,
}
LEGACY_GENERATED = {
    "tpot-analyzer/data/community_archive/snapshots/"
    "20260730T045247Z-4913d0183e39/enriched_tweets.parquet",
    "tpot-analyzer/data/community_archive/snapshots/"
    "20260730T045247Z-4913d0183e39/manifest.json",
}


@dataclass
class Report:
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    metrics: list[str] = field(default_factory=list)

    def check(self, label: str, ok: bool, detail: str) -> None:
        print(f"{'✓' if ok else '✗'} {label}: {detail}")
        self.passed += int(ok)
        self.failed += int(not ok)

    def warn(self, label: str, detail: str) -> None:
        print(f"⚠ {label}: {detail}")
        self.warnings += 1


def run(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=text, check=False,
    )


def git(root: Path, *args: str) -> str:
    result = run(root, "git", *args)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def file_sha256(file_name: Path) -> str:
    digest = hashlib.sha256()
    with file_name.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n").rstrip(b"\n")


def blob(root: Path, revision: str, file_name: str) -> bytes | None:
    result = run(root, "git", "show", f"{revision}:{file_name}", text=False)
    return result.stdout if result.returncode == 0 else None


def is_subsequence(earlier: bytes, later: bytes) -> bool:
    remaining = iter(normalized(later).splitlines())
    return all(any(candidate == line for candidate in remaining)
               for line in normalized(earlier).splitlines())


def is_ledger_union(file_name: str, earlier: bytes, later: bytes) -> bool:
    if file_name.endswith("ROADMAP.md"):
        earlier = b"\n".join(
            line for line in earlier.splitlines()
            if not line.startswith(b"*Last updated:")
        )
        later = b"\n".join(
            line for line in later.splitlines()
            if not line.startswith(b"*Last updated:")
        )
    return is_subsequence(earlier, later)


def verify_integration(root: Path, report: Report, require_pushed: bool) -> None:
    head = git(root, "rev-parse", "HEAD")
    branch = git(root, "branch", "--show-current")
    status = run(root, "git", "status", "--porcelain=v1", "-z", text=False).stdout
    unmerged = git(root, "diff", "--name-only", "--diff-filter=U").splitlines()
    whitespace = run(root, "git", "diff", "--check", f"{BASE_MAIN}..HEAD")
    report.check("canonical worktree clean", not status, f"dirty_bytes={len(status)}")
    report.check("no unmerged paths", not unmerged, f"paths={len(unmerged)}")
    report.check(
        "integration whitespace gate",
        whitespace.returncode == 0,
        whitespace.stdout.strip() or "git diff --check passed",
    )
    report.check(
        "integration branch",
        branch in {"main", "codex/main-integration-20260823"},
        branch,
    )
    for name, revision in PRESERVED_REFS.items():
        actual = run(root, "git", "rev-parse", "--verify", name)
        oid = actual.stdout.strip() if actual.returncode == 0 else "missing"
        report.check(f"preserved ref {name}", oid == revision, oid)
        contained = run(root, "git", "merge-base", "--is-ancestor", revision, head)
        expected_in_main = revision != SNAPSHOT and revision != STASH
        report.check(
            f"disposition {name}",
            (contained.returncode == 0) == expected_in_main,
            "integrated" if contained.returncode == 0 else "preserved-only",
        )
        remote_ref = f"refs/remotes/origin/{name}"
        report.check(
            f"recovery ref not pushed {name}",
            run(root, "git", "show-ref", "--verify", remote_ref).returncode != 0,
            remote_ref,
        )

    parent = git(root, "rev-parse", f"{SNAPSHOT}^")
    paths = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", parent, SNAPSHOT).splitlines()
    exact = 0
    normalized_only = 0
    unioned = 0
    for file_name in paths:
        before = blob(root, SNAPSHOT, file_name)
        after = blob(root, "HEAD", file_name)
        if before == after:
            exact += 1
        elif before is not None and after is not None and normalized(before) == normalized(after):
            normalized_only += 1
        elif file_name in {
            "tpot-analyzer/docs/ROADMAP.md",
            "tpot-analyzer/docs/WORKLOG.md",
        } and before and after:
            unioned += int(is_ledger_union(file_name, before, after))
    coverage_ok = (exact, normalized_only, unioned, len(paths)) == (47, 2, 2, 51)
    report.check(
        "51-path snapshot coverage", coverage_ok,
        f"exact={exact}, whitespace_only={normalized_only}, unioned={unioned}, total={len(paths)}",
    )
    origin_main = git(root, "rev-parse", "refs/remotes/origin/main")
    if require_pushed:
        report.check("HEAD pushed to origin/main", head == origin_main, origin_main)
    else:
        ahead = git(root, "rev-list", "--count", f"{origin_main}..HEAD")
        report.warn("push check deferred", f"HEAD is {ahead} commits ahead of origin/main")
    report.metrics.extend((f"head: {head}", f"branch: {branch}"))


def verify_recovery(root: Path, legacy: Path, bundle: Path, report: Report) -> None:
    stash = run(root, "git", "rev-parse", "refs/stash")
    stash_oid = stash.stdout.strip() if stash.returncode == 0 else "missing"
    report.check("parked stash retained", stash_oid == STASH, stash_oid)
    report.check(
        "parked stash excluded from HEAD",
        run(root, "git", "merge-base", "--is-ancestor", STASH, "HEAD").returncode == 1,
        STASH,
    )
    report.check("standalone bundle exists", bundle.is_file(), str(bundle))
    if bundle.is_file():
        report.check("standalone bundle hash", file_sha256(bundle) == BUNDLE_SHA256, file_sha256(bundle))
        verified = run(root, "git", "bundle", "verify", str(bundle))
        report.check("standalone bundle verifies", verified.returncode == 0, f"rc={verified.returncode}")

    raw_root = legacy / ".codex-worktrees/raw-first-retrieval"
    raw_status = run(raw_root, "git", "status", "--porcelain=v1", "-z", text=False)
    status_hash = hashlib.sha256(raw_status.stdout).hexdigest()
    report.check("raw snapshot source unchanged", status_hash == RAW_STATUS_SHA256, status_hash)


def historical_match(root: Path, file_name: str, content: bytes) -> bool:
    current = blob(root, "HEAD", file_name)
    if current is not None and normalized(current) == normalized(content):
        return True
    revisions = git(root, "log", "--all", "--format=%H", "--", file_name).splitlines()
    for revision in dict.fromkeys(revisions):
        candidate = blob(root, revision, file_name)
        if candidate is not None and normalized(candidate) == normalized(content):
            return True
    return False


def verify_legacy(root: Path, legacy: Path, report: Report) -> None:
    raw = run(legacy, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all", text=False).stdout
    records = [record for record in raw.split(b"\0") if record]
    tracked = [record for record in records if not record.startswith(b"??")]
    untracked = [record for record in records if record.startswith(b"??")]
    paths = [record[3:].decode("utf-8", "surrogateescape") for record in records]
    excluded = [
        file_name for file_name in paths
        if "sync-conflict-" in file_name
        or file_name.startswith(".codex-worktrees/")
        or file_name in LEGACY_GENERATED
    ]
    candidates = [file_name for file_name in paths if file_name not in excluded]
    unmatched: list[str] = []
    for file_name in candidates:
        source = legacy / file_name
        if not source.is_file():
            unmatched.append(file_name)
            continue
        if not historical_match(root, file_name, source.read_bytes()):
            unmatched.append(file_name)
    expected_counts = (len(tracked), len(untracked), len(excluded), len(candidates))
    report.check(
        "legacy inventory counts",
        expected_counts == (657, 705, 657, 705),
        f"tracked={len(tracked)}, untracked={len(untracked)}, excluded={len(excluded)}, candidates={len(candidates)}",
    )
    report.check(
        "legacy unique intentional residue",
        not unmatched,
        f"unmatched={len(unmatched)}" + (f", sample={unmatched[:5]}" if unmatched else ""),
    )
    report.warn(
        "legacy checkout remains quarantined and dirty",
        f"dirty={len(records)}, excluded_residue={len(excluded)}, represented={len(candidates)}",
    )
