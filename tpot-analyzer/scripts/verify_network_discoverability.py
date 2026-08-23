"""Verify frozen network-discoverability assumptions without mutating inputs."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.artifacts.digests import file_sha256
from src.artifacts.frozen_manifest import verify_frozen_manifest
from src.config import DEFAULT_DATA_DIR
from src.evaluation.discoverability import (
    FIXED_SEED_PRESET,
    load_and_measure_frozen,
    write_json_no_clobber,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = PROJECT_ROOT / "docs" / "seed_presets.json"


def _print_report(report: dict) -> None:
    h1 = report["hypotheses"]["H-D1"]["measurements"]
    h2 = report["hypotheses"]["H-D2"]["measurements"]
    h5 = report["hypotheses"]["H-D5"]["measurements"]
    print(
        "✓ H-D1 capture bias measured: "
        f"centers={h1['capture_centers']:,} "
        f"({h1['capture_center_node_pct']:.3f}% nodes), "
        f"shadow-center edges={h1['shadow_edges_touching_center_pct']:.3f}%, "
        f"degree-1 nodes={h1['degree_one_node_pct']:.3f}%"
    )
    components, reach = h2["components"], h2["seed_reachability"]
    print(
        "✓ H-D2 topology semantics measured: "
        f"weak giant={components['weak']['giant_pct']:.3f}%, "
        f"strong giant={components['strong']['giant_pct']:.3f}%, "
        f"mutual giant={components['mutual']['giant_pct']:.3f}%"
    )
    print(
        "  Seed reachability: "
        f"forward={reach['forward']['pct']:.3f}%, "
        f"reverse={reach['reverse']['pct']:.3f}%, "
        f"undirected={reach['undirected']['pct']:.3f}%, "
        f"mutual={reach['mutual']['pct']:.3f}%"
    )
    print(
        "✓ H-D5 selection bias measured: "
        f"core={h5['core_nodes']:,}, halo={h5['halo_only_nodes']:,}, "
        f"selected={h5['selected_nodes']:,}, "
        f"exact={h5['exact_core_halo_match']}, "
        "degree gap="
        + (
            f"{h5['high_minus_degree_one_selection_pp']:.3f}pp"
            if h5["high_minus_degree_one_selection_pp"] is not None
            else "unavailable"
        )
    )
    for name, hypothesis in report["hypotheses"].items():
        mark = "✗" if hypothesis["falsified"] else "✓"
        verdict = "FALSIFIED" if hypothesis["falsified"] else "not falsified"
        print(f"{mark} {name}: {verdict}")


def verify(
    data_dir: Path,
    *,
    json_out: Path | None = None,
    strict: bool = False,
    seed_file: Path = SEED_FILE,
) -> int:
    """Complete measurements by default; optionally enforce falsifiers."""
    print("Frozen network discoverability verification")
    print(f"Data directory: {Path(data_dir).resolve()}")
    try:
        # This identity gate must precede every scientific input read.
        manifest = verify_frozen_manifest(data_dir)
        report = load_and_measure_frozen(data_dir, seed_file)
        report["provenance"] = {
            "bundle_id": manifest.get("bundle_id"),
            "seed_preset": FIXED_SEED_PRESET,
            "seed_file_sha256": file_sha256(seed_file),
        }
        if json_out is not None:
            write_json_no_clobber(json_out, report)
            print(f"✓ Wrote no-clobber JSON result: {json_out.resolve()}")
        _print_report(report)
    except Exception as exc:
        print(f"✗ Discoverability measurement failed: {type(exc).__name__}: {exc}")
        print("Next step: inspect the named input; do not weaken its identity gate.")
        return 1

    print("✓ Measurement completed; findings do not fail default verification.")
    if strict and not report["strict_pass"]:
        print("✗ Strict mode: a predeclared hypothesis was falsified.")
        return 2
    print("Untested follow-ups:")
    for item in report["follow_ups_not_run"]:
        print(f"  - {item}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure discoverability assumptions on the pinned frozen graph"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    raise SystemExit(verify(args.data_dir, json_out=args.json_out, strict=args.strict))


if __name__ == "__main__":
    main()
