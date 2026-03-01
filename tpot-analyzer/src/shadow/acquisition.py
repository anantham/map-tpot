"""Active-learning acquisition scorer for shadow scraping candidate selection.

Ranks candidates by expected information gain per scrape-minute, then
diversifies via Maximal Marginal Relevance (MMR) so a single batch doesn't
spend its budget on near-duplicate accounts.

Score formula (before time normalisation):
    score_i = (
        w_entropy          * H(p_i)           # multi-class entropy of community membership
      + w_boundary         * boundary_i       # 1 - (p_max1 - p_max2): bridge/boundary signal
      + w_influence        * log(1+deg_i)     # normalised follower count
      + w_novelty          * novelty_i        # 1 - max cosine sim to already-scraped set
      + w_coverage_boost   * coverage_i       # inverse of smallest-community size
    ) / expected_scrape_time_i

All five signals are independently normalised to [0, 1] before weighting.
Accounts with missing data receive conservative defaults that still rank
them *above* well-understood accounts (unknown = high uncertainty = priority).
"""
from __future__ import annotations

import logging
import sqlite3
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from .enricher import SeedAccount
from ..data.shadow_store import ShadowStore

LOGGER = logging.getLogger(__name__)

# Epsilon to avoid log(0)
_EPS = 1e-12

# Proxy scrape-time constants (for accounts never scraped before)
_PROXY_SECS_PER_FOLLOWER = 1.0 / 500.0
_PROXY_BASE_SECS = 30.0
_SCRAPE_TIME_FLOOR = 30.0
_SCRAPE_TIME_CAP = 3600.0

# Number of recent successful runs to use for expected scrape time
_RECENT_RUNS = 3


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AcquisitionWeights:
    """Weights for the acquisition score composite.  Must sum to 1.0."""

    entropy: float = 0.35
    boundary: float = 0.25
    influence: float = 0.20
    novelty: float = 0.15
    coverage_boost: float = 0.05

    def __post_init__(self) -> None:
        total = (
            self.entropy + self.boundary + self.influence
            + self.novelty + self.coverage_boost
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"AcquisitionWeights must sum to 1.0, got {total:.6f}. "
                f"(entropy={self.entropy}, boundary={self.boundary}, "
                f"influence={self.influence}, novelty={self.novelty}, "
                f"coverage_boost={self.coverage_boost})"
            )


@dataclass(frozen=True)
class CandidateSignals:
    """Per-candidate signals and derived scores."""

    account_id: str
    entropy: float           # H(p_i) normalised to [0, 1]
    boundary: float          # 1 - (p_max1 - p_max2)
    influence: float         # log(1 + followers) normalised to [0, 1]
    novelty: float           # 1 - max cosine sim to scraped set
    coverage_boost: float    # 1 / (1 + min_community_size), normalised
    expected_scrape_time: float   # seconds
    raw_score: float         # weighted composite, before time normalisation
    final_score: float       # raw_score / expected_scrape_time


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_div(a: float, b: float, fallback: float = 0.0) -> float:
    return a / b if b > 0 else fallback


def _normalize_array(arr: np.ndarray) -> np.ndarray:
    """Min-max normalise a 1-D array to [0, 1]; returns zeros if range is 0."""
    lo, hi = arr.min(), arr.max()
    if hi - lo < _EPS:
        return np.zeros_like(arr, dtype=float)
    return (arr - lo) / (hi - lo)


def _multiclass_entropy(weights: List[float], k: int) -> float:
    """Normalised multi-class Shannon entropy, range [0, 1].

    weights — community membership weights for one account (need not sum to 1).
    k       — number of communities (sets the normalisation denominator).
    """
    if not weights or k <= 1:
        return 0.0
    arr = np.array(weights, dtype=float)
    total = arr.sum()
    if total <= _EPS:
        return 1.0  # no information → maximum uncertainty
    p = arr / total
    h = -np.sum(p * np.log2(p + _EPS))
    max_h = np.log2(k)
    return float(np.clip(h / max_h, 0.0, 1.0))


def _boundary_signal(sorted_weights: List[float]) -> float:
    """Boundary signal = 1 - (p_max1 - p_max2), clamped to [0, 1].

    A score near 1 means the top two communities are equally weighted
    (bridging account); near 0 means one community dominates.
    """
    if not sorted_weights:
        return 1.0  # no data → assume bridge
    total = sum(sorted_weights)
    if total <= _EPS:
        return 1.0
    p = [w / total for w in sorted_weights]
    p0 = p[0] if len(p) > 0 else 0.0
    p1 = p[1] if len(p) > 1 else 0.0
    return float(np.clip(1.0 - (p0 - p1), 0.0, 1.0))


def _resolve_run_id(community_conn: sqlite3.Connection, run_id: Optional[str]) -> Optional[str]:
    """Return the given run_id or the latest one from community_run."""
    if run_id is not None:
        return run_id
    row = community_conn.execute(
        "SELECT run_id FROM community_run ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        LOGGER.warning("No NMF runs found in community_run — entropy/boundary signals will use defaults")
        return None
    return row[0]


# ---------------------------------------------------------------------------
# Signal fetchers (all batched)
# ---------------------------------------------------------------------------

def _fetch_entropy_boundary(
    community_conn: sqlite3.Connection,
    run_id: str,
    candidate_ids: List[str],
    k: int,
) -> Dict[str, tuple[float, float]]:
    """Return {account_id: (entropy, boundary)} for all candidate_ids.

    Accounts absent from community_membership get (1.0, 1.0) — max uncertainty.
    """
    if not candidate_ids:
        return {}

    placeholders = ",".join("?" * len(candidate_ids))
    rows = community_conn.execute(
        f"SELECT account_id, weight FROM community_membership"
        f" WHERE run_id = ? AND account_id IN ({placeholders})"
        f" ORDER BY account_id, weight DESC",
        [run_id, *candidate_ids],
    ).fetchall()

    # Group by account
    by_account: Dict[str, List[float]] = {}
    for account_id, weight in rows:
        by_account.setdefault(account_id, []).append(float(weight))

    result: Dict[str, tuple[float, float]] = {}
    for aid in candidate_ids:
        ws = by_account.get(aid, [])
        if not ws:
            result[aid] = (1.0, 1.0)  # unknown → max uncertainty
        else:
            result[aid] = (
                _multiclass_entropy(ws, k),
                _boundary_signal(ws),  # already sorted DESC by SQL
            )
    return result


def _fetch_k(community_conn: sqlite3.Connection, run_id: str) -> int:
    """Fetch K (number of communities) for a given run_id."""
    row = community_conn.execute(
        "SELECT k FROM community_run WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return 1
    return max(1, int(row[0]))


def _fetch_followers(
    shadow_store: ShadowStore,
    candidate_ids: List[str],
    community_conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Optional[int]]:
    """Return {account_id: followers_count} for each candidate.

    Primary source: shadow_account.followers_count (real Twitter follower count).
    Fallback for accounts absent from shadow_account: COUNT(*) from
    account_followers in community_conn — the number of archive accounts that
    follow this person, a good within-TPOT influence proxy.
    """
    if not candidate_ids:
        return {}
    from sqlalchemy.sql import text as sa_text

    def _op(engine):
        placeholders = ",".join(f":id{i}" for i in range(len(candidate_ids)))
        params = {f"id{i}": aid for i, aid in enumerate(candidate_ids)}
        with engine.connect() as conn:
            rows = conn.execute(
                sa_text(
                    f"SELECT account_id, followers_count FROM shadow_account"
                    f" WHERE account_id IN ({placeholders})"
                ),
                params,
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    result = shadow_store._execute_with_retry("fetch_followers", _op)

    # Fill in missing accounts from archive account_followers table
    missing = [aid for aid in candidate_ids if result.get(aid) is None]
    if missing and community_conn is not None:
        placeholders = ",".join("?" * len(missing))
        rows = community_conn.execute(
            f"SELECT account_id, COUNT(*) FROM account_followers"
            f" WHERE account_id IN ({placeholders})"
            f" GROUP BY account_id",
            missing,
        ).fetchall()
        for aid, count in rows:
            if result.get(aid) is None:
                result[aid] = int(count)
        n_filled = sum(1 for aid in missing if result.get(aid) is not None)
        if n_filled:
            LOGGER.debug(
                "Follower fallback: filled %d/%d missing accounts from account_followers",
                n_filled, len(missing),
            )

    return result


def _fetch_scrape_times(
    shadow_store: ShadowStore,
    candidate_ids: List[str],
    followers_map: Dict[str, Optional[int]],
) -> Dict[str, float]:
    """Return {account_id: expected_scrape_seconds} for each candidate.

    For cold-start accounts (never scraped), a proxy based on follower count
    is used: followers / 500 + 30, clamped to [30, 3600].
    """
    if not candidate_ids:
        return {}

    from sqlalchemy.sql import text as sa_text

    def _op(engine):
        placeholders = ",".join(f":id{i}" for i in range(len(candidate_ids)))
        params = {f"id{i}": aid for i, aid in enumerate(candidate_ids)}
        with engine.connect() as conn:
            rows = conn.execute(
                sa_text(
                    f"SELECT seed_account_id, duration_seconds"
                    f" FROM scrape_run_metrics"
                    f" WHERE seed_account_id IN ({placeholders})"
                    f"   AND skipped = 0"
                    f" ORDER BY seed_account_id, run_at DESC",
                ),
                params,
            ).fetchall()
        return rows

    rows = shadow_store._execute_with_retry("fetch_scrape_times", _op)

    # Group by account, take median of last N runs
    by_account: Dict[str, List[float]] = {}
    for seed_id, duration in rows:
        if seed_id not in by_account:
            by_account[seed_id] = []
        if len(by_account[seed_id]) < _RECENT_RUNS:
            by_account[seed_id].append(float(duration))

    result: Dict[str, float] = {}
    known_followers = [v for v in followers_map.values() if v is not None]
    median_followers = statistics.median(known_followers) if known_followers else 500

    for aid in candidate_ids:
        if aid in by_account and by_account[aid]:
            secs = statistics.median(by_account[aid])
        else:
            fcount = followers_map.get(aid) or median_followers
            secs = _PROXY_SECS_PER_FOLLOWER * float(fcount) + _PROXY_BASE_SECS
        result[aid] = float(np.clip(secs, _SCRAPE_TIME_FLOOR, _SCRAPE_TIME_CAP))
    return result


def _fetch_coverage_boost(
    community_conn: sqlite3.Connection,
    candidate_ids: List[str],
) -> Dict[str, float]:
    """Return {account_id: coverage_boost} using community_account table.

    coverage_boost_i = 1 / (1 + size_of_smallest_community_that_account_belongs_to)
    """
    if not candidate_ids:
        return {}

    # Get community sizes
    sizes_rows = community_conn.execute(
        "SELECT community_id, COUNT(*) FROM community_account GROUP BY community_id"
    ).fetchall()
    community_size: Dict[str, int] = {r[0]: int(r[1]) for r in sizes_rows}

    # Get each candidate's communities
    placeholders = ",".join("?" * len(candidate_ids))
    assign_rows = community_conn.execute(
        f"SELECT account_id, community_id FROM community_account"
        f" WHERE account_id IN ({placeholders})",
        candidate_ids,
    ).fetchall()

    by_account: Dict[str, List[int]] = {}
    for aid, cid in assign_rows:
        by_account.setdefault(aid, []).append(community_size.get(cid, 1))

    result: Dict[str, float] = {}
    for aid in candidate_ids:
        sizes = by_account.get(aid, [])
        if sizes:
            result[aid] = 1.0 / (1.0 + min(sizes))
        else:
            result[aid] = 1.0  # not in any community → max priority
    return result


def _build_membership_vectors(
    community_conn: sqlite3.Connection,
    run_id: str,
    account_ids: List[str],
    k: int,
) -> Dict[str, np.ndarray]:
    """Return {account_id: normalised K-dim membership vector}."""
    if not account_ids or k == 0:
        return {}

    placeholders = ",".join("?" * len(account_ids))
    rows = community_conn.execute(
        f"SELECT account_id, community_idx, weight FROM community_membership"
        f" WHERE run_id = ? AND account_id IN ({placeholders})",
        [run_id, *account_ids],
    ).fetchall()

    vectors: Dict[str, np.ndarray] = {aid: np.zeros(k) for aid in account_ids}
    for aid, cidx, w in rows:
        if aid in vectors and 0 <= cidx < k:
            vectors[aid][cidx] = float(w)

    # L2-normalise
    for aid in vectors:
        norm = np.linalg.norm(vectors[aid])
        if norm > _EPS:
            vectors[aid] = vectors[aid] / norm
    return vectors


def _compute_novelty(
    candidate_ids: List[str],
    candidate_vectors: Dict[str, np.ndarray],
    scraped_ids: List[str],
    scraped_vectors: Dict[str, np.ndarray],
    k: int,
) -> Dict[str, float]:
    """Return {account_id: novelty} — 1 minus max cosine sim to scraped set.

    Accounts with no community data get novelty = 1.0 (fully novel).
    """
    if not candidate_ids:
        return {}

    # Build candidate matrix
    C = np.stack([candidate_vectors[aid] for aid in candidate_ids])  # (n_cand, K)

    if not scraped_ids or not any(
        np.any(scraped_vectors[aid] != 0) for aid in scraped_ids if aid in scraped_vectors
    ):
        return {aid: 1.0 for aid in candidate_ids}

    S = np.stack([
        scraped_vectors.get(aid, np.zeros(k)) for aid in scraped_ids
    ])  # (n_scraped, K)

    # cosine sim: both matrices are already L2-normalised
    sim_matrix = C @ S.T  # (n_cand, n_scraped)
    max_sim = sim_matrix.max(axis=1)  # (n_cand,)
    novelty_vals = np.clip(1.0 - max_sim, 0.0, 1.0)

    result: Dict[str, float] = {}
    for i, aid in enumerate(candidate_ids):
        if np.all(candidate_vectors[aid] == 0):
            result[aid] = 1.0  # no community data → fully novel
        else:
            result[aid] = float(novelty_vals[i])
    return result


# ---------------------------------------------------------------------------
# MMR selection
# ---------------------------------------------------------------------------

def _mmr_select(
    candidates: List[SeedAccount],
    scores: Dict[str, float],
    membership_vectors: Dict[str, np.ndarray],
    top_k: int,
    lambda_mmr: float,
    k: int,
) -> List[SeedAccount]:
    """Greedy MMR: iteratively pick candidate maximising
        λ * score_i − (1 − λ) * max_{j ∈ selected} cosine_sim(i, j).

    Complexity: O(top_k × n) — acceptable for n ≤ 500.
    """
    top_k = min(top_k, len(candidates))
    if top_k <= 0:
        return []

    remaining = list(candidates)
    selected: List[SeedAccount] = []
    selected_vectors: List[np.ndarray] = []

    for _ in range(top_k):
        if not remaining:
            break

        best_seed = None
        best_val = float("-inf")

        for seed in remaining:
            relevance = scores.get(seed.account_id, 0.0)
            v = membership_vectors.get(seed.account_id, np.zeros(k))

            if selected_vectors:
                sims = np.array([float(v @ sv) for sv in selected_vectors])
                redundancy = float(sims.max())
            else:
                redundancy = 0.0

            mmr_val = lambda_mmr * relevance - (1.0 - lambda_mmr) * redundancy
            if mmr_val > best_val:
                best_val = mmr_val
                best_seed = seed

        if best_seed is not None:
            selected.append(best_seed)
            selected_vectors.append(membership_vectors.get(best_seed.account_id, np.zeros(k)))
            remaining = [s for s in remaining if s.account_id != best_seed.account_id]

    # Append any remaining candidates (if top_k == len(candidates) this won't trigger)
    selected_ids = {s.account_id for s in selected}
    selected.extend(s for s in candidates if s.account_id not in selected_ids)
    return selected


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_candidates(
    candidates: Sequence[SeedAccount],
    shadow_store: ShadowStore,
    community_conn: sqlite3.Connection,
    run_id: Optional[str] = None,
    weights: Optional[AcquisitionWeights] = None,
    top_k: Optional[int] = None,
    lambda_mmr: float = 0.7,
) -> List[SeedAccount]:
    """Return candidates ranked by acquisition score, MMR-diversified.

    Args:
        candidates:      Accounts to score; typically the full seed list.
        shadow_store:    ShadowStore wrapping shadow.db (for followers + metrics).
        community_conn:  sqlite3.Connection to archive_tweets.db.
        run_id:          NMF run to use for membership signals; None = latest.
        weights:         Custom signal weights (default: AcquisitionWeights()).
        top_k:           Return only the top-k accounts; None = all ranked.
        lambda_mmr:      MMR trade-off: 1.0 = pure relevance, 0.0 = max diversity.

    Returns:
        Candidates in descending score order, diversified by MMR.
    """
    if not candidates:
        return []

    w = weights or AcquisitionWeights()
    candidate_list = list(candidates)
    candidate_ids = [c.account_id for c in candidate_list]

    # ── Resolve NMF run ──────────────────────────────────────────────────────
    resolved_run_id = _resolve_run_id(community_conn, run_id)
    k = _fetch_k(community_conn, resolved_run_id) if resolved_run_id else 1

    LOGGER.debug(
        "Acquisition scoring: %d candidates, run_id=%s, K=%d",
        len(candidate_ids), resolved_run_id, k,
    )

    # ── Batch-fetch all signals ───────────────────────────────────────────────

    # 1. Entropy + boundary
    if resolved_run_id:
        entropy_boundary = _fetch_entropy_boundary(
            community_conn, resolved_run_id, candidate_ids, k
        )
    else:
        entropy_boundary = {aid: (1.0, 1.0) for aid in candidate_ids}

    # 2. Influence (followers) — with archive fallback for cold-start accounts
    followers_map = _fetch_followers(shadow_store, candidate_ids, community_conn)

    # 3. Expected scrape time
    scrape_times = _fetch_scrape_times(shadow_store, candidate_ids, followers_map)

    # 4. Coverage boost (Layer 2)
    coverage_raw = _fetch_coverage_boost(community_conn, candidate_ids)

    # 5. Membership vectors (for novelty + MMR)
    if resolved_run_id:
        cand_vectors = _build_membership_vectors(
            community_conn, resolved_run_id, candidate_ids, k
        )
    else:
        cand_vectors = {aid: np.zeros(max(k, 1)) for aid in candidate_ids}

    # Novelty: compare candidates against already-scraped accounts
    # "Scraped" = accounts that appear in scrape_run_metrics with skipped=False
    scraped_ids_in_batch = [
        aid for aid in candidate_ids
        if aid in scrape_times and scrape_times[aid] < _SCRAPE_TIME_CAP
        # proxy: accounts with at least one real run have a measured time
    ]
    # Strictly: accounts with a row in scrape_run_metrics (not proxy-estimated)
    # We distinguish via comparing with proxy formula
    known_follower_vals = [v for v in followers_map.values() if v is not None]
    median_f = statistics.median(known_follower_vals) if known_follower_vals else 500

    def _is_proxy(aid: str) -> bool:
        f = followers_map.get(aid) or median_f
        proxy = float(np.clip(
            _PROXY_SECS_PER_FOLLOWER * float(f) + _PROXY_BASE_SECS,
            _SCRAPE_TIME_FLOOR, _SCRAPE_TIME_CAP,
        ))
        return abs(scrape_times.get(aid, proxy) - proxy) < 0.5

    actual_scraped = [aid for aid in candidate_ids if not _is_proxy(aid)]
    novelty_map = _compute_novelty(
        candidate_ids, cand_vectors,
        actual_scraped, cand_vectors, k,
    )

    # ── Normalise signals ─────────────────────────────────────────────────────

    # entropy — already in [0, 1] by construction
    entropy_arr = np.array([entropy_boundary[aid][0] for aid in candidate_ids])
    # boundary — already in [0, 1]
    boundary_arr = np.array([entropy_boundary[aid][1] for aid in candidate_ids])

    # influence — log(1 + followers), then normalise by batch max
    raw_followers = np.array([
        float(followers_map.get(aid) or 0) for aid in candidate_ids
    ])
    influence_arr = np.log1p(raw_followers)
    influence_arr = _normalize_array(influence_arr)

    # novelty — already in [0, 1]
    novelty_arr = np.array([novelty_map[aid] for aid in candidate_ids])

    # coverage_boost — normalise within batch
    coverage_arr = np.array([coverage_raw[aid] for aid in candidate_ids])
    coverage_arr = _normalize_array(coverage_arr)

    # ── Composite score ───────────────────────────────────────────────────────
    raw_scores = (
        w.entropy * entropy_arr
        + w.boundary * boundary_arr
        + w.influence * influence_arr
        + w.novelty * novelty_arr
        + w.coverage_boost * coverage_arr
    )

    time_arr = np.array([scrape_times[aid] for aid in candidate_ids])
    final_scores = raw_scores / time_arr  # per second of expected cost

    score_map: Dict[str, float] = {
        aid: float(final_scores[i]) for i, aid in enumerate(candidate_ids)
    }

    LOGGER.debug(
        "Score distribution — min=%.4f  max=%.4f  mean=%.4f",
        final_scores.min(), final_scores.max(), final_scores.mean(),
    )

    # ── Sort by final score descending ────────────────────────────────────────
    sorted_candidates = sorted(
        candidate_list,
        key=lambda s: score_map.get(s.account_id, 0.0),
        reverse=True,
    )

    # ── MMR diversification ───────────────────────────────────────────────────
    effective_k = top_k if top_k is not None else len(sorted_candidates)
    result = _mmr_select(
        sorted_candidates,
        score_map,
        cand_vectors,
        effective_k,
        lambda_mmr,
        k,
    )

    LOGGER.info(
        "Acquisition scorer: ranked %d candidates (top_k=%s, λ_mmr=%.2f)",
        len(result), top_k, lambda_mmr,
    )
    if LOGGER.isEnabledFor(logging.DEBUG):
        for rank, seed in enumerate(result[:10], 1):
            LOGGER.debug(
                "  #%d %s  score=%.5f  entropy=%.3f  boundary=%.3f"
                "  novelty=%.3f  influence=%.3f  coverage=%.3f  time=%.0fs",
                rank, seed.username or seed.account_id,
                score_map.get(seed.account_id, 0.0),
                entropy_boundary[seed.account_id][0],
                entropy_boundary[seed.account_id][1],
                novelty_map[seed.account_id],
                float(influence_arr[candidate_ids.index(seed.account_id)]),
                float(coverage_arr[candidate_ids.index(seed.account_id)]),
                scrape_times[seed.account_id],
            )

    return result
