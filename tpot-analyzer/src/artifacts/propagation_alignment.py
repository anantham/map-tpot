"""Select and align propagation artifacts to an authoritative graph order."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from src.artifacts.digests import ordered_node_digest
from src.artifacts.propagation_schema import (
    NODE_ARRAY_KEYS,
    REQUIRED_KEYS,
    validate_propagation_shapes,
)


class ArtifactCompatibilityError(ValueError):
    """Raised when no propagation artifact is safe for a graph."""


@dataclass(frozen=True)
class CandidateEvaluation:
    path: Path
    source_node_count: int | None
    matched_node_count: int
    missing_node_count: int | None
    exact_order: bool
    reason: str


@dataclass(frozen=True)
class AlignedPropagation:
    path: Path
    graph_node_ids: np.ndarray
    arrays: dict[str, np.ndarray]
    source_node_count: int
    exact_order: bool
    graph_node_sha256: str
    source_node_sha256: str
    evaluations: tuple[CandidateEvaluation, ...]


@dataclass
class _CompatibleCandidate:
    path: Path
    source_node_ids: np.ndarray
    arrays: dict[str, np.ndarray]
    exact_order: bool
    evaluation: CandidateEvaluation
    candidate_index: int


def _string_ids(values: np.ndarray, *, label: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ArtifactCompatibilityError(
            f"{label} node_ids must be one-dimensional; got shape={array.shape}"
        )
    normalized = np.asarray([str(value) for value in array])
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in normalized:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ArtifactCompatibilityError(
            f"duplicate {label} node IDs: sample={duplicates[:5]}"
        )
    return normalized


def _load_candidate(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    with np.load(path, allow_pickle=False) as payload:
        missing = sorted(REQUIRED_KEYS - set(payload.files))
        if missing:
            raise ArtifactCompatibilityError(
                f"missing propagation arrays: {missing}"
            )
        arrays = {key: np.asarray(payload[key]) for key in payload.files}
    source_ids = _string_ids(arrays["node_ids"], label="source")
    n_source = len(source_ids)
    try:
        validate_propagation_shapes(arrays, n_source)
    except ValueError as exc:
        raise ArtifactCompatibilityError(str(exc)) from exc
    return source_ids, arrays


def _evaluate_candidate(
    path: Path,
    graph_ids: np.ndarray,
    candidate_index: int,
) -> tuple[CandidateEvaluation, _CompatibleCandidate | None]:
    if not path.is_file():
        evaluation = CandidateEvaluation(
            path=path,
            source_node_count=None,
            matched_node_count=0,
            missing_node_count=None,
            exact_order=False,
            reason="file not found",
        )
        return evaluation, None
    try:
        source_ids, arrays = _load_candidate(path)
    except (ArtifactCompatibilityError, OSError, ValueError) as exc:
        evaluation = CandidateEvaluation(
            path=path,
            source_node_count=None,
            matched_node_count=0,
            missing_node_count=None,
            exact_order=False,
            reason=str(exc),
        )
        return evaluation, None

    source_index = {node_id: index for index, node_id in enumerate(source_ids)}
    missing = [node_id for node_id in graph_ids if node_id not in source_index]
    matched = len(graph_ids) - len(missing)
    exact_order = np.array_equal(source_ids, graph_ids)
    if missing:
        reason = (
            f"matched={matched}/{len(graph_ids)}, missing={len(missing)}, "
            f"sample={missing[:5]}"
        )
        evaluation = CandidateEvaluation(
            path=path,
            source_node_count=len(source_ids),
            matched_node_count=matched,
            missing_node_count=len(missing),
            exact_order=False,
            reason=reason,
        )
        return evaluation, None

    reason = "exact graph order" if exact_order else "full coverage; reindex required"
    evaluation = CandidateEvaluation(
        path=path,
        source_node_count=len(source_ids),
        matched_node_count=matched,
        missing_node_count=0,
        exact_order=exact_order,
        reason=reason,
    )
    return evaluation, _CompatibleCandidate(
        path=path,
        source_node_ids=source_ids,
        arrays=arrays,
        exact_order=exact_order,
        evaluation=evaluation,
        candidate_index=candidate_index,
    )


def select_aligned_propagation(
    graph_node_ids: np.ndarray,
    adjacency: sp.spmatrix,
    candidate_paths: list[Path],
) -> AlignedPropagation:
    graph_ids = _string_ids(graph_node_ids, label="graph")
    if adjacency.ndim != 2 or adjacency.shape != (len(graph_ids), len(graph_ids)):
        raise ArtifactCompatibilityError(
            "adjacency shape must be square and match graph node_ids: "
            f"adjacency={adjacency.shape}, nodes={len(graph_ids)}"
        )
    if not candidate_paths:
        raise ArtifactCompatibilityError("No propagation candidate paths were provided")

    evaluations: list[CandidateEvaluation] = []
    compatible: list[_CompatibleCandidate] = []
    for index, path in enumerate(candidate_paths):
        evaluation, candidate = _evaluate_candidate(Path(path), graph_ids, index)
        evaluations.append(evaluation)
        if candidate is not None:
            compatible.append(candidate)
    if not compatible:
        detail = "; ".join(
            f"{evaluation.path}: {evaluation.reason}"
            for evaluation in evaluations
        )
        raise ArtifactCompatibilityError(
            f"No propagation artifact covers the graph node universe; {detail}"
        )

    # Candidate order expresses scientific intent (for example production
    # before legacy fallback). Exact order is only a transport optimization.
    selected = min(compatible, key=lambda candidate: candidate.candidate_index)
    if selected.exact_order:
        aligned_indices = np.arange(len(graph_ids))
    else:
        source_index = {
            node_id: index
            for index, node_id in enumerate(selected.source_node_ids)
        }
        aligned_indices = np.asarray(
            [source_index[node_id] for node_id in graph_ids],
            dtype=np.int64,
        )

    aligned_arrays = dict(selected.arrays)
    for key in NODE_ARRAY_KEYS & aligned_arrays.keys():
        aligned_arrays[key] = aligned_arrays[key][aligned_indices]
    aligned_arrays["node_ids"] = graph_ids
    return AlignedPropagation(
        path=selected.path,
        graph_node_ids=graph_ids,
        arrays=aligned_arrays,
        source_node_count=len(selected.source_node_ids),
        exact_order=selected.exact_order,
        graph_node_sha256=ordered_node_digest(graph_ids),
        source_node_sha256=ordered_node_digest(selected.source_node_ids),
        evaluations=tuple(evaluations),
    )
