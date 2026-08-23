"""Read-only named-seed evidence and acquisition-cost coverage report."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.evaluation.seed_coverage_contract import (
    SeedCoverageInputError,
    hypothesis_results,
    validate_seed_panel,
)
from src.evaluation.seed_coverage_content import snapshot_content
from src.evaluation.seed_coverage_follow import build_seed_follow_rows
from src.evaluation.seed_coverage_io import (
    database_receipt,
    load_json_input,
    lookup_usernames,
)
from src.graph.source_selectivity import rank_follow_candidates


def open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    """Open and pin a WAL-aware SQLite read snapshot without write capability."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise SeedCoverageInputError(f"SQLite input does not exist: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise SeedCoverageInputError(
                f"SQLite input did not enter query-only mode: {resolved}"
            )
        connection.execute("BEGIN")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except (SeedCoverageInputError, sqlite3.Error):
        connection.close()
        raise
    return connection


def build_seed_coverage_report(
    *,
    seed_panel_path: Path,
    cache_db_path: Path,
    archive_db_path: Path,
    archive_snapshot_dir: Path,
    api_price_card_path: Path,
    top_k: int = 25,
) -> dict[str, Any]:
    """Build one network-free query-time report from explicit data inputs."""
    if type(top_k) is not int or top_k <= 0:
        raise SeedCoverageInputError("top_k must be a positive integer")

    try:
        panel, panel_receipt = load_json_input(seed_panel_path)
        price_card, price_receipt = load_json_input(api_price_card_path)
    except ValueError as exc:
        raise SeedCoverageInputError(str(exc)) from exc
    seeds = validate_seed_panel(panel)
    if price_card.get("schema_version") != 1 or not price_card.get("card_id"):
        raise SeedCoverageInputError("price card requires schema_version=1 and card_id")

    content, snapshot_receipt = snapshot_content(archive_snapshot_dir, seeds)
    archive = open_readonly_sqlite(archive_db_path)
    try:
        cache = open_readonly_sqlite(cache_db_path)
    except Exception:
        archive.close()
        raise
    try:
        archive_receipt = database_receipt(archive_db_path, archive)
        cache_receipt = database_receipt(cache_db_path, cache)
        seed_aliases = {
            alias: seed["account_id"]
            for seed in seeds
            for alias in (
                seed["account_id"],
                f"shadow:{seed['handle_at_freeze'].lower().lstrip('@')}",
            )
        }
        seed_rows, ranking_edges = build_seed_follow_rows(
            archive, cache, seeds, price_card, content, seed_aliases
        )
        ranking = rank_follow_candidates(
            [seed["account_id"] for seed in seeds],
            ranking_edges,
            {
                seed["account_id"]: seed.get("claimed_following")
                for seed in seeds
            },
        )
        names = lookup_usernames(
            archive,
            cache,
            [candidate.account_id for candidate in ranking.candidates[:top_k]],
        )
        handles = {
            seed["account_id"]: seed["handle_at_freeze"] for seed in seeds
        }
        diagnostics = {
            row.seed_id: {
                "observed_out_degree": row.observed_out_degree,
                "claimed_following_count": row.claimed_following_count,
                "effective_degree": row.effective_degree,
                "degree_unknown": row.degree_unknown,
            }
            for row in ranking.seed_diagnostics
        }
        for row in seed_rows:
            row["source_selectivity_diagnostic"] = diagnostics[row["account_id"]]
        candidates = [
            {
                "account_id": candidate.account_id,
                "username_candidates": names.get(candidate.account_id, []),
                "selectivity_score": candidate.selectivity_score,
                "raw_support": candidate.raw_support,
                "supporting_seeds": [
                    handles.get(seed_id, seed_id)
                    for seed_id in candidate.supporting_seeds
                ],
            }
            for candidate in ranking.candidates[:top_k]
        ]
        report = {
            "report_schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "boundary": (
                "Observed stored identity keys and content rows only. Follow source "
                "attribution is absent for the merged SQLite views; scores are not "
                "membership, probability, confidence, endorsement, or "
                "retrieval-quality evidence."
            ),
            "inputs": {
                "seed_panel": {
                    **panel_receipt,
                    "panel_id": panel["panel_id"],
                    "panel_version": panel["panel_version"],
                },
                "api_price_card": {
                    **price_receipt,
                    "card_id": price_card["card_id"],
                    "verified_at": price_card.get("verified_at"),
                    "official_sources": price_card.get("official_sources", []),
                },
                "archive_db": archive_receipt,
                "cache_db": cache_receipt,
                "archive_snapshot": snapshot_receipt,
                "cross_db_atomicity": (
                    "archive and cache each use a read transaction, but the two "
                    "SQLite snapshots are not mutually atomic"
                ),
            },
            "seeds": seed_rows,
            "ranking": {
                "method": "source_selectivity_v1",
                "semantic_status": "uncalibrated_ranking_signal",
                "ranking_input": "distinct stored-key union across available follow views",
                "candidate_count": len(ranking.candidates),
                "returned_top_k": min(top_k, len(ranking.candidates)),
                "top_candidates": candidates,
            },
        }
        report["hypotheses"] = hypothesis_results(seed_rows, ranking.candidates)
        return report
    except (ValueError, sqlite3.Error) as exc:
        if isinstance(exc, SeedCoverageInputError):
            raise
        raise SeedCoverageInputError(str(exc)) from exc
    finally:
        for connection in (archive, cache):
            try:
                connection.rollback()
            finally:
                connection.close()
