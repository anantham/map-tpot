"""Stable hashes for ordered node universes, files, and CSR matrices."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import scipy.sparse as sp


def ordered_node_digest(node_ids: Iterable[object]) -> str:
    digest = hashlib.sha256()
    count = 0
    for raw_value in node_ids:
        value = str(raw_value).encode("utf-8")
        digest.update(len(value).to_bytes(8, byteorder="big", signed=False))
        digest.update(value)
        count += 1
    digest.update(count.to_bytes(8, byteorder="big", signed=False))
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csr_digests(matrix: sp.spmatrix) -> tuple[str, str]:
    canonical = matrix.tocsr(copy=True)
    canonical.sum_duplicates()
    canonical.sort_indices()
    shape_bytes = np.asarray(canonical.shape, dtype="<i8").tobytes()
    indptr_bytes = np.asarray(canonical.indptr, dtype="<i8").tobytes()
    indices_bytes = np.asarray(canonical.indices, dtype="<i8").tobytes()
    values_bytes = np.asarray(canonical.data, dtype="<f8").tobytes()

    structure = hashlib.sha256()
    structure.update(shape_bytes)
    structure.update(indptr_bytes)
    structure.update(indices_bytes)

    values = hashlib.sha256()
    values.update(shape_bytes)
    values.update(values_bytes)
    return structure.hexdigest(), values.hexdigest()


def json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
