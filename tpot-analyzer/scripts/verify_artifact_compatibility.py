"""Verify the frozen graph-to-TPOT artifact chain before experiments."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.artifacts.frozen_control_verifier import verify_frozen_control
from src.artifacts.frozen_manifest import verify_frozen_manifest
from src.artifacts.frozen_output_verifier import verify_frozen_outputs
from src.config import DEFAULT_DATA_DIR


def verify(data_dir: Path) -> int:
    """Run human-readable compatibility checks; return a process exit code."""
    print("Frozen graph artifact compatibility verification")
    print(f"Data directory: {data_dir.resolve()}")
    try:
        manifest = verify_frozen_manifest(data_dir)
        control = verify_frozen_control(
            data_dir,
            selected_propagation=manifest["selected_propagation"],
        )
        verify_frozen_outputs(data_dir, control)
    except Exception as exc:
        print(f"✗ Compatibility verification failed: {type(exc).__name__}: {exc}")
        print(
            "Next step: inspect the named artifact; rebuild only after its node "
            "domain, ordering, and source provenance are understood."
        )
        return 1

    print(
        "Next step: run controlled assumption experiments against this "
        "compatibility-checked, hash-pinned frozen bundle."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify frozen graph artifact compatibility before experiments"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    raise SystemExit(verify(args.data_dir))


if __name__ == "__main__":
    main()
