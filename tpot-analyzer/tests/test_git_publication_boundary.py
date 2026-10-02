"""Test intent: deny future private artifact publication by path without reading
records; permit source changes and explicit synthetic/config data allowlist.
"""
import pytest

from scripts.check_publication_files import publication_path_allowed


@pytest.mark.parametrize("path", [
    "tpot-analyzer/data/evals/phase1_membership_audit_accounts.json",
    "tpot-analyzer/data/tpot_holdout_seeds.json", "tpot-analyzer/data/novel_dossier.json",
    "tpot-analyzer/public-site/public/data.json", "tpot-analyzer/secrets/cookies.json",
    "Related data/private.csv", "tpot-analyzer/cache.pkl", "tpot-analyzer/local.sqlite3",
    "../escape.py",
    "tpot-analyzer/private/export.json", "exports/user.parquet",
    "tpot-analyzer/exports/account.csv", "tpot-analyzer/private/notes.txt",
    "tpot-analyzer/private/helper.py", "tpot-analyzer/src/snapshot.parquet",
    "tpot-analyzer/config/unreviewed.json", "/tpot-analyzer/src/example.py",
    "tpot-analyzer/src/../private.py", "tpot-analyzer/src/private/export.json",
])
def test_private_artifact_paths_denied(path):
    assert not publication_path_allowed(path)


@pytest.mark.parametrize("path", ["tpot-analyzer/src/archive/fetcher.py", "tpot-analyzer/data/.gitkeep",
                                  "tpot-analyzer/data/golden/taxonomy.yaml", "tpot-analyzer/tests/test_example.py"])
def test_source_and_explicit_config_paths_allowed(path):
    assert publication_path_allowed(path)


@pytest.mark.parametrize("path", [
    ".github/workflows/test.yml", ".gitignore", "AGENTS.md", "README.md",
    "tpot-analyzer/Makefile", "tpot-analyzer/requirements.txt",
    "tpot-analyzer/config/publication_fields.json", "tpot-analyzer/docs/diagnostics/security-review.md",
    "tpot-analyzer/scripts/_export_helpers/example.py", "tpot-analyzer/public-site/package-lock.json",
    "tpot-analyzer/public-site/api/example.js", "tpot-analyzer/public-site/scripts/example.node-test.mjs",
    "tpot-analyzer/public-site/__tests__/api/example.cjs", "tpot-analyzer/public-site/src/example.jsx",
    "tpot-analyzer/graph-explorer/src/researchNotes/example.css", "tpot-analyzer/graph-explorer/vercel.json",
])
def test_known_source_config_and_text_locations_allowed(path):
    assert publication_path_allowed(path)


def test_explicit_zero_or_empty_ci_base_fails_closed(monkeypatch):
    from scripts.check_publication_files import changed_paths
    for base in ("0" * 40, ""):
        with pytest.raises(ValueError, match="real commit"):
            changed_paths(base=base)


def test_synthetic_git_branch_diff_rejects_private_artifact(tmp_path, monkeypatch):
    import subprocess
    from scripts.check_publication_files import changed_paths
    monkeypatch.chdir(tmp_path)
    def git(*arguments):
        return subprocess.check_output(["git", *arguments]).decode().strip()
    git("init", "-q")
    (tmp_path / "source.py").write_text("# synthetic source\n")
    git("add", "source.py")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    private = tmp_path / "tpot-analyzer" / "data" / "evals" / "synthetic.json"
    private.parent.mkdir(parents=True)
    private.write_text("[]")
    git("add", str(private.relative_to(tmp_path)))
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "-qm", "synthetic forbidden artifact")
    paths = changed_paths(base=base)
    assert paths == ["tpot-analyzer/data/evals/synthetic.json"]
    assert not publication_path_allowed(paths[0])
