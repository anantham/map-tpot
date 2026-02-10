"""Reporting helpers for shadow subset audit."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from .constants import now_utc


def summarize_overlap(local: Set[str], remote: Set[str]) -> Dict[str, object]:
    overlap = local & remote
    missing = remote - local
    extra = local - remote
    coverage = (len(overlap) / len(remote) * 100.0) if remote else None
    precision = (len(overlap) / len(local) * 100.0) if local else None
    return {
        "local_count": len(local),
        "remote_count": len(remote),
        "overlap_count": len(overlap),
        "missing_in_local_count": len(missing),
        "extra_in_local_count": len(extra),
        "coverage_pct": round(coverage, 3) if coverage is not None else None,
        "precision_pct": round(precision, 3) if precision is not None else None,
        "missing_in_local": sorted(missing),
        "extra_in_local": sorted(extra),
    }


def _mean_coverage(results: Sequence[Dict[str, object]], relation_key: str) -> Optional[float]:
    values: List[float] = []
    for entry in results:
        relation_data = entry.get(relation_key)
        if not isinstance(relation_data, dict):
            continue
        summary = relation_data.get("summary")
        if not isinstance(summary, dict):
            continue
        value = summary.get("coverage_pct")
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def write_report(
    *,
    output_path: Path,
    db_path: Path,
    total_targets: int,
    total_remote_requests: int,
    results: Sequence[Dict[str, object]],
    is_complete: bool,
) -> Dict[str, object]:
    follower_cov = _mean_coverage(results, "followers")
    following_cov = _mean_coverage(results, "followings")
    report = {
        "generated_at": now_utc(),
        "db_path": str(db_path),
        "targets": total_targets,
        "total_remote_requests": total_remote_requests,
        "average_coverage_pct": {
            "followers": follower_cov,
            "followings": following_cov,
        },
        "progress": {
            "completed_accounts": len(results),
            "total_accounts": total_targets,
            "is_complete": is_complete,
        },
        "results": list(results),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    return report
