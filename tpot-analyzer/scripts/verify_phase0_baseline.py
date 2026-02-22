"""Phase 0 verifier: config flags + docs anchors + artifact presence."""
from __future__ import annotations

import json
from pathlib import Path


def status_line(ok: bool, label: str) -> str:
    return f"{'✓' if ok else '✗'} {label}"


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    docs_dir = project_root / "docs"
    adr_path = docs_dir / "adr" / "007-observation-aware-clustering-membership.md"
    settings_path = project_root / "config" / "graph_settings.json"
    spectral_npz = project_root / "data" / "graph_snapshot.spectral.npz"
    nodes_parquet = project_root / "data" / "graph_snapshot.nodes.parquet"
    edges_parquet = project_root / "data" / "graph_snapshot.edges.parquet"

    lines: list[str] = []

    lines.append(status_line(adr_path.exists(), f"ADR 007 present at {adr_path}"))
    lines.append(status_line(settings_path.exists(), f"Settings file present at {settings_path}"))

    settings_payload = {}
    if settings_path.exists():
        try:
            settings_payload = json.loads(settings_path.read_text())
        except Exception:
            settings_payload = {}

    settings = settings_payload.get("settings") if isinstance(settings_payload, dict) else {}
    if not isinstance(settings, dict):
        settings = {}

    required_keys = [
        "hierarchy_engine",
        "membership_engine",
        "obs_weighting",
        "obs_p_min",
        "obs_completeness_floor",
    ]
    missing = [key for key in required_keys if key not in settings]
    lines.append(status_line(not missing, f"Math/observability flags configured (missing={missing or 'none'})"))

    lines.append(status_line(nodes_parquet.exists(), f"Nodes snapshot exists ({nodes_parquet})"))
    lines.append(status_line(edges_parquet.exists(), f"Edges snapshot exists ({edges_parquet})"))
    lines.append(status_line(spectral_npz.exists(), f"Spectral sidecar exists ({spectral_npz})"))

    print("Phase 0 Baseline Verification")
    print("=" * 34)
    for line in lines:
        print(line)

    print("\nMetrics")
    print("- Config flags found:", len(required_keys) - len(missing), "/", len(required_keys))
    print("- Settings mode:", settings.get("obs_weighting", "unknown"))
    print("- Hierarchy engine:", settings.get("hierarchy_engine", "unknown"))
    print("- Membership engine:", settings.get("membership_engine", "unknown"))

    failures = [line for line in lines if line.startswith("✗")]
    print("\nNext steps")
    if failures:
        print("- Resolve failed checks before enabling new hierarchy or membership engines.")
        print("- Re-run: python -m scripts.verify_phase0_baseline")
        raise SystemExit(1)

    print("- Baseline checks passed. Continue with observation-aware adjacency validation.")


if __name__ == "__main__":
    main()
