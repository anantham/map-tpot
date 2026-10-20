"""Exercise release data checks through the CLI in disposable Git repositories."""
from pathlib import Path
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts" / "verify_shareable_checkout.py"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True)


def repo(tmp_path):
    git(tmp_path, "init", "-q")
    project = tmp_path / "tpot-analyzer"
    project.mkdir()
    (tmp_path / ".gitignore").write_bytes((PROJECT.parent / ".gitignore").read_bytes())
    (project / ".gitignore").write_bytes((PROJECT / ".gitignore").read_bytes())
    return project


def verify(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
                          capture_output=True, text=True)


def test_default_ignore_keeps_unknown_capture_private(tmp_path):
    project = repo(tmp_path)
    (project / "data").mkdir()
    (project / "data" / "new-capture.json").write_text('{"synthetic":true}')
    git(tmp_path, "add", ".")
    result = verify(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "0 entries, 0 unexpected" in result.stdout


def test_force_tracked_private_data_is_refused_even_when_ignored(tmp_path):
    project = repo(tmp_path)
    (project / "data" / "private").mkdir(parents=True)
    capture = project / "data" / "private" / "synthetic.json"
    capture.write_text('{"synthetic":true}')
    git(tmp_path, "add", "--force", "tpot-analyzer/data/private/synthetic.json")
    result = verify(tmp_path)
    assert result.returncode == 1
    assert "1 entries, 1 unexpected" in result.stdout
    assert capture.read_text() == '{"synthetic":true}'


def test_historical_public_price_configuration_can_still_be_tracked(tmp_path):
    project = repo(tmp_path)
    manifest = project / "data" / "manifests" / "twitterapiio_price_card_20260730.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"synthetic":true}')
    git(tmp_path, "add", ".")
    result = verify(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "1 entries, 0 unexpected" in result.stdout


def test_root_research_archive_is_refused_without_deleting_the_local_file(tmp_path):
    repo(tmp_path)
    capture = tmp_path / "Related data" / "synthetic.zip"
    capture.parent.mkdir()
    capture.write_bytes(b"invented archive fixture")
    git(tmp_path, "add", "--force", "Related data/synthetic.zip")
    result = verify(tmp_path)
    assert result.returncode == 1
    assert "1 entries, 1 unexpected" in result.stdout
    assert capture.read_bytes() == b"invented archive fixture"
