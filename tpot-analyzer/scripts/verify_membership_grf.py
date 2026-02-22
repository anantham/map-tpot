"""Verify GRF membership primitives and anchor-label readiness."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
from scipy import sparse

from src.data.account_tags import AccountTagStore
from src.graph.membership_grf import GRFMembershipConfig, compute_grf_membership


def status(ok: bool, label: str) -> str:
    return f"{'✓' if ok else '✗'} {label}"


def verify_settings(project_root: Path) -> tuple[list[str], dict]:
    lines: list[str] = []
    settings_path = project_root / "config" / "graph_settings.json"
    lines.append(status(settings_path.exists(), f"Settings file exists: {settings_path}"))
    payload = {}
    if settings_path.exists():
        try:
            payload = json.loads(settings_path.read_text())
        except Exception:
            payload = {}

    settings = payload.get("settings") if isinstance(payload, dict) else {}
    if not isinstance(settings, dict):
        settings = {}

    lines.append(status("membership_engine" in settings, "settings.membership_engine present"))
    lines.append(status("obs_weighting" in settings, "settings.obs_weighting present"))
    return lines, settings


def verify_solver() -> tuple[list[str], dict]:
    lines: list[str] = []
    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )

    result = compute_grf_membership(
        adjacency=adjacency,
        positive_anchor_indices=[0],
        negative_anchor_indices=[2],
        config=GRFMembershipConfig(prior=0.5),
    )
    midpoint = float(result.probabilities[1])
    lines.append(status(0.45 <= midpoint <= 0.55, f"Midpoint score is balanced: {midpoint:.4f}"))
    lines.append(status(result.converged or result.cg_info > 0, f"CG solve executed (info={result.cg_info})"))
    lines.append(status(result.total_uncertainty[0] == 0.0, "Anchors have zero uncertainty"))

    metrics = {
        "midpoint_probability": midpoint,
        "cg_info": result.cg_info,
        "cg_iterations": result.cg_iterations,
        "prior": result.prior,
    }
    return lines, metrics


def verify_anchor_aggregation() -> tuple[list[str], dict]:
    lines: list[str] = []
    with tempfile.TemporaryDirectory(prefix="verify-membership-") as tmp:
        db_path = Path(tmp) / "account_tags.db"
        store = AccountTagStore(db_path)
        store.upsert_tag(ego="ego1", account_id="a", tag="tpot", polarity=1)
        store.upsert_tag(ego="ego1", account_id="b", tag="not", polarity=-1)
        store.upsert_tag(ego="ego1", account_id="c", tag="plus", polarity=1)
        store.upsert_tag(ego="ego1", account_id="c", tag="minus", polarity=-1)
        anchors = sorted(store.list_anchor_polarities(ego="ego1"))

    lines.append(status(("a", 1) in anchors, "Positive anchor aggregation works"))
    lines.append(status(("b", -1) in anchors, "Negative anchor aggregation works"))
    lines.append(status(("c", 1) not in anchors and ("c", -1) not in anchors, "Tie polarity is excluded"))
    metrics = {
        "anchor_rows": len(anchors),
        "anchors": anchors,
    }
    return lines, metrics


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    settings_lines, settings = verify_settings(project_root)
    solver_lines, solver_metrics = verify_solver()
    anchor_lines, anchor_metrics = verify_anchor_aggregation()

    all_lines = settings_lines + solver_lines + anchor_lines
    failures = [line for line in all_lines if line.startswith("✗")]

    print("GRF Membership Verification")
    print("=" * 27)
    for line in all_lines:
        print(line)

    print("\nMetrics")
    print(f"- membership_engine: {settings.get('membership_engine', 'missing')}")
    print(f"- obs_weighting: {settings.get('obs_weighting', 'missing')}")
    print(f"- midpoint_probability: {solver_metrics['midpoint_probability']:.4f}")
    print(f"- cg_info: {solver_metrics['cg_info']}")
    print(f"- cg_iterations: {solver_metrics['cg_iterations']}")
    print(f"- aggregated_anchor_rows: {anchor_metrics['anchor_rows']}")

    print("\nNext steps")
    if failures:
        print("- Fix failed checks before enabling membership_engine=grf in production.")
        print("- Re-run: python -m scripts.verify_membership_grf")
        raise SystemExit(1)

    print("- GRF primitives are healthy.")
    print("- Enable via config: settings.membership_engine = 'grf'")
    print("- Query endpoint: GET /api/clusters/accounts/<id>/membership?ego=<handle>")


if __name__ == "__main__":
    main()
