#!/usr/bin/env python3
"""Verify the entropy correction and independent-band fail-closed boundary."""

from __future__ import annotations

import argparse
import hashlib
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.propagation.bands import (
    IndependentBandingUndefinedError,
    UnboundAccountBandError,
    propagation_artifact_mode,
    reject_unbound_account_band_table,
    require_supported_band_mode,
)
from src.propagation.entropy import normalized_row_entropy

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _historical_entropy(affinities: np.ndarray) -> np.ndarray:
    """Reproduce the quarantined scale-dependent formula for diagnostics."""
    clipped = np.clip(affinities, 1e-12, None)
    contributions = np.where(
        affinities > 1e-10,
        clipped * np.log(clipped),
        0.0,
    )
    return -contributions.sum(axis=1) / math.log(affinities.shape[1])


def _stored_band_metrics(db_path: Path) -> tuple[Check, dict[str, object]]:
    if not db_path.exists():
        return (
            Check("Stored legacy bands inspected", False, f"missing DB: {db_path}"),
            {},
        )
    uri = f"file:{db_path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='account_band'"
        ).fetchone()
        if not has_table:
            return (
                Check(
                    "Stored legacy bands inspected",
                    True,
                    "account_band table absent; no stale rows can be reused",
                ),
                {},
            )
        counts = dict(
            conn.execute(
                "SELECT band, COUNT(*) FROM account_band GROUP BY band"
            ).fetchall()
        )
        negative = conn.execute(
            "SELECT COUNT(*) FROM account_band WHERE entropy < 0"
        ).fetchone()[0]
        created = conn.execute(
            "SELECT MIN(created_at), MAX(created_at) FROM account_band"
        ).fetchone()
    metrics = {
        "counts": counts,
        "negative_entropy_rows": negative,
        "created_at": list(created),
    }
    return (
        Check(
            "Stored legacy bands inspected",
            True,
            f"rows={sum(counts.values()):,}, negative_entropy={negative:,}",
        ),
        metrics,
    )


def verify(npz_path: Path, db_path: Path | None) -> tuple[list[Check], dict]:
    checks: list[Check] = []
    metrics: dict[str, object] = {}
    if not npz_path.exists():
        return [
            Check("Propagation artifact found", False, f"missing: {npz_path}")
        ], metrics

    checks.append(
        Check(
            "Propagation artifact found",
            True,
            f"{npz_path} sha256={_sha256(npz_path)[:16]}…",
        )
    )
    with np.load(str(npz_path), allow_pickle=False) as artifact:
        mode = propagation_artifact_mode(artifact)
        memberships = np.asarray(artifact["memberships"], dtype=np.float64)
        community_key = (
            "community_names"
            if "community_names" in artifact
            else "community_ids"
        )
        community_count = len(artifact[community_key])

    affinities = memberships[:, :community_count]
    corrected = normalized_row_entropy(affinities)
    historical = _historical_entropy(affinities)
    outside = int(((historical < 0) | (historical > 1)).sum())
    corrected_outside = int(((corrected < 0) | (corrected > 1)).sum())
    metrics.update(
        {
            "mode": mode,
            "accounts": len(affinities),
            "communities": community_count,
            "historical_entropy_range": [
                float(historical.min()),
                float(historical.max()),
            ],
            "historical_outside_unit_interval": outside,
            "corrected_entropy_range": [
                float(corrected.min()),
                float(corrected.max()),
            ],
        }
    )
    checks.append(
        Check(
            "Corrected entropy is finite and bounded",
            bool(np.all(np.isfinite(corrected)) and corrected_outside == 0),
            (
                f"range={corrected.min():.6f}..{corrected.max():.6f}; "
                f"outside[0,1]={corrected_outside:,}"
            ),
        )
    )
    scaled = normalized_row_entropy(affinities * 7.0)
    max_scale_delta = float(np.max(np.abs(corrected - scaled)))
    metrics["max_scale_delta"] = max_scale_delta
    checks.append(
        Check(
            "Entropy is invariant to affinity units",
            bool(np.allclose(corrected, scaled, atol=1e-12)),
            f"max_delta_after_7x_scale={max_scale_delta:.3e}",
        )
    )

    guard_passed = False
    guard_detail = f"mode={mode} remains supported"
    try:
        require_supported_band_mode(mode)
    except IndependentBandingUndefinedError as exc:
        guard_passed = mode == "independent"
        guard_detail = str(exc)
    checks.append(
        Check(
            "Independent display bands fail closed",
            guard_passed if mode == "independent" else True,
            guard_detail,
        )
    )

    unbound_guard_passed = False
    unbound_guard_detail = "unbound account_band rows remain consumable"
    try:
        reject_unbound_account_band_table("verification")
    except UnboundAccountBandError as exc:
        unbound_guard_passed = True
        unbound_guard_detail = str(exc)
    checks.append(
        Check(
            "Unbound account_band consumers fail closed",
            unbound_guard_passed,
            unbound_guard_detail,
        )
    )

    if db_path is not None:
        band_check, band_metrics = _stored_band_metrics(db_path)
        checks.append(band_check)
        metrics["stored_account_band"] = band_metrics
    return checks, metrics


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify independent Lift entropy and band quarantine"
    )
    parser.add_argument(
        "--npz-path",
        type=Path,
        default=ROOT / "data" / "community_propagation.npz",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "archive_tweets.db",
    )
    args = parser.parse_args()

    checks, metrics = verify(args.npz_path, args.db_path)
    print("Independent Band Entropy Verification")
    print("=" * 42)
    for check in checks:
        print(f"{'✓' if check.passed else '✗'} {check.name}: {check.detail}")
    failures = [check for check in checks if not check.passed]
    print("-" * 42)
    print(
        f"Checks: {len(checks)} | Passed: {len(checks) - len(failures)} | "
        f"Failed: {len(failures)}"
    )
    print(f"Metrics: {metrics}")
    print(
        "Boundary: read-only audit only; no NPZ, SQLite, public export, "
        "frontier ranking, or paid acquisition was written."
    )
    if failures:
        print("Next: resolve the named artifact or contract failure, then rerun.")
        return 1
    print(
        "Next: define specialist/bridge semantics on development judgments, "
        "then beat Lift-plus-seed-neighbor baselines on a frozen holdout before "
        "regenerating account_band."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
