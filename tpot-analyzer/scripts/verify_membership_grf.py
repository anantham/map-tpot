"""Verify GRF affinity primitives and anchor-label readiness."""
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
    parse_error: str | None = None
    if settings_path.exists():
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
            payload = {}

    lines.append(
        status(
            parse_error is None,
            (
                f"Settings JSON parsed: {settings_path}"
                if parse_error is None
                else f"Settings JSON parse failed: {settings_path}: {parse_error}"
            ),
        )
    )
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
    midpoint = float(result.affinities[1])
    lines.append(status(0.45 <= midpoint <= 0.55, f"Midpoint affinity is balanced: {midpoint:.4f}"))
    solver_ok = result.converged and result.cg_info == 0
    lines.append(
        status(
            solver_ok,
            (
                "CG solve converged"
                if solver_ok
                else f"CG solve did not converge (info={result.cg_info})"
            ),
        )
    )
    lines.append(status(result.total_uncertainty[0] == 0.0, "Anchors have zero uncertainty"))

    metrics = {
        "midpoint_affinity": midpoint,
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

    lines.append(status(("a", 1) in anchors, "Legacy positive anchor aggregation works"))
    lines.append(status(("b", -1) in anchors, "Legacy negative anchor aggregation works"))
    lines.append(status(("c", 1) not in anchors and ("c", -1) not in anchors, "Legacy tie polarity is excluded"))
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

    print("GRF Affinity Verification")
    print("=" * 27)
    for line in all_lines:
        print(line)

    print("\nSummary")
    print(f"- checks: {len(all_lines)}")
    print(f"- passed: {len(all_lines) - len(failures)}")
    print(f"- failed: {len(failures)}")

    print("\nMetrics")
    print(f"- membership_engine: {settings.get('membership_engine', 'missing')}")
    print(f"- obs_weighting: {settings.get('obs_weighting', 'missing')}")
    print(f"- midpoint_affinity: {solver_metrics['midpoint_affinity']:.4f}")
    print(f"- cg_info: {solver_metrics['cg_info']}")
    print(f"- cg_iterations: {solver_metrics['cg_iterations']}")
    print(f"- aggregated_anchor_rows: {anchor_metrics['anchor_rows']}")

    print("\nNext steps")
    if failures:
        print("- Fix failed checks before enabling membership_engine=grf in production.")
        print("- Re-run: python -m scripts.verify_membership_grf")
        raise SystemExit(1)

    print("- GRF numerical primitives passed this synthetic smoke check.")
    print("- Keep membership_engine=grf experimental/feature-flagged.")
    print("- This legacy anchor smoke check is ego-scoped, not ontology/task/community-target-scoped.")
    print("- Block real overlapping-subculture inference until cross-target isolation passes.")
    print("- Require held-out calibration and MNAR diagnostics before probability or default-use claims.")


if __name__ == "__main__":
    main()
