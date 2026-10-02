"""CI hygiene inspects source conflicts without scanning private dataset contents."""
import importlib.util
import subprocess
import sys
from pathlib import Path


def test_conflict_hygiene_scopes_source_and_avoids_private_data(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts/verify_ci_discovery.py"
    spec = importlib.util.spec_from_file_location("ci_security_scope", source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name in ("tpot-analyzer/data/synthetic.md", "Related data/synthetic.py",
                 "docs/private/synthetic.md", "docs/dossiers/synthetic.py",
                 "tpot-analyzer/docs/private/synthetic.py", "tpot-analyzer/docs/dossiers/synthetic.md"):
        private = tmp_path / name
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text("<<<<<<< synthetic sentinel\n")
    code = tmp_path / "tpot-analyzer/src/synthetic.py"
    code.parent.mkdir(parents=True)
    code.write_text("pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    checks = []
    class Capture:
        def check(self, label, ok, detail):
            checks.append((label, ok, detail))
    module.verify_patch_hygiene(Capture(), None)
    assert next(ok for label, ok, _ in checks if label == "tracked conflict markers")
    code.write_text("<<<<<<< conflicting source\n")
    checks.clear()
    module.verify_patch_hygiene(Capture(), None)
    assert not next(ok for label, ok, _ in checks if label == "tracked conflict markers")
