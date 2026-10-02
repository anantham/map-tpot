"""Non-executable, bounded numeric/string NPZ artifact storage."""
from __future__ import annotations

import ast
import io
import json
import re
import struct
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import scipy.sparse as sp

MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_NODES = 2_000_000
MAX_EDGES = 50_000_000


def string_array(values, *, label: str = "identities") -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1 or len(array) > MAX_NODES:
        raise ValueError(f"{label} must be a bounded one-dimensional array")
    if any(not isinstance(value, (str, int, np.integer)) or isinstance(value, bool) or
           not str(value).strip() or len(str(value)) > 1024 for value in array):
        raise ValueError(f"{label} must contain nonempty bounded strings or integers")
    return array.astype(str)


def _npy_header(stream, entry_bytes: int) -> None:
    """Check the allocation encoded in the header before NumPy sees it."""
    if stream.read(6) != b"\x93NUMPY":
        raise ValueError("artifact array has invalid NPY magic")
    version = tuple(stream.read(2))
    if version not in {(1, 0), (2, 0), (3, 0)}:
        raise ValueError("artifact array has unsupported NPY version")
    length_bytes = 2 if version == (1, 0) else 4
    encoded_length = stream.read(length_bytes)
    if len(encoded_length) != length_bytes:
        raise ValueError("artifact array has truncated NPY header")
    header_length = struct.unpack("<H" if length_bytes == 2 else "<I", encoded_length)[0]
    if header_length > 16_384:
        raise ValueError("artifact NPY header exceeds byte limit")
    header = stream.read(header_length)
    if len(header) != header_length:
        raise ValueError("artifact array has truncated NPY header")
    try:
        record = ast.literal_eval(header.decode("utf-8" if version == (3, 0) else "latin1"))
    except (ValueError, SyntaxError, RecursionError) as exc:
        raise ValueError("artifact NPY header is invalid") from exc
    if not isinstance(record, dict) or set(record) != {"shape", "descr", "fortran_order"}:
        raise ValueError("artifact NPY header fields are invalid")
    descr = record["descr"]
    if isinstance(descr, str) and "O" in descr:
        raise ValueError("Object arrays are forbidden in artifacts")
    if not isinstance(descr, str) or len(descr) > 32 or not re.fullmatch(r"[<>=|][biufUS][0-9]+", descr):
        raise ValueError("artifact NPY dtype must be numeric or string")
    dtype = np.dtype(descr)
    shape = record["shape"]
    if (not isinstance(shape, tuple) or len(shape) > 8 or
            any(type(dimension) is not int or dimension < 0 or dimension > MAX_EXPANDED_BYTES for dimension in shape) or
            type(record["fortran_order"]) is not bool or not 1 <= dtype.itemsize <= 1_048_576):
        raise ValueError("artifact NPY shape/dtype is invalid")
    elements = 1
    for dimension in shape:
        elements *= dimension  # Python integers cannot wrap around.
        if elements > MAX_EDGES:
            raise ValueError("artifact NPY allocation exceeds element limit")
    expected_bytes = elements * dtype.itemsize
    if expected_bytes > MAX_EXPANDED_BYTES:
        raise ValueError("artifact NPY allocation exceeds expanded byte limit")
    if stream.tell() + expected_bytes != entry_bytes:
        raise ValueError("artifact NPY header/data byte length mismatch")


def _zip_directory_bounds(handle) -> None:
    """Bound central-directory parsing before ZipFile constructs entry objects."""
    size = os.fstat(handle.fileno()).st_size
    if size < 22:
        raise ValueError("artifact ZIP end record is missing")
    handle.seek(-22, os.SEEK_END)
    end = handle.read(22)
    fields = struct.unpack("<4s4H2LH", end)
    magic, disk, directory_disk, disk_entries, entries, directory_bytes, offset, comment_bytes = fields
    if (magic != b"PK\x05\x06" or disk or directory_disk or disk_entries != entries or
            entries > 64 or directory_bytes > 65536 or comment_bytes or offset + directory_bytes != size - 22):
        raise ValueError("artifact ZIP central directory exceeds supported bounds")
    handle.seek(0)


class SafeArrays(dict):
    """In-memory equivalent of the legacy NpzFile context API."""
    @property
    def files(self):
        return list(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def close(self):
        pass


def load_npz_arrays(path: Path, *, require_finite: bool = True) -> dict[str, np.ndarray]:
    """Read bounded immutable NPY bytes with validated allocation headers."""
    path = Path(path)
    if path.suffix.lower() != ".npz" or path.is_symlink():
        raise ValueError("artifact must be a non-symlink NPZ; regenerate legacy pickle artifacts")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    arrays = SafeArrays()
    with os.fdopen(descriptor, "rb") as handle:
        if os.fstat(handle.fileno()).st_size > MAX_COMPRESSED_BYTES:
            raise ValueError("artifact exceeds compressed byte limit")
        _zip_directory_bounds(handle)
        with zipfile.ZipFile(handle) as archive:
            entries = archive.infolist()
            if len(entries) > 64 or len({entry.filename for entry in entries}) != len(entries):
                raise ValueError("artifact contains excessive or duplicate arrays")
            if any(not entry.filename.endswith(".npy") or not 1 <= len(entry.filename[:-4]) <= 128 or "/" in entry.filename or "\\" in entry.filename
                   or entry.flag_bits & 1 for entry in entries):
                raise ValueError("artifact contains unsupported archive entries")
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("artifact exceeds expanded byte limit")
            for entry in entries:
                with archive.open(entry) as stream:
                    _npy_header(stream, entry.file_size)
                    stream.seek(0)
                    raw = stream.read(entry.file_size + 1)
                if len(raw) != entry.file_size:
                    raise ValueError("artifact entry byte length mismatch")
                # Recheck the copied bytes; later file replacement/in-place writes
                # cannot alter the header NumPy actually loads.
                _npy_header(io.BytesIO(raw), len(raw))
                array = np.load(io.BytesIO(raw), allow_pickle=False, max_header_size=16_384)
                if require_finite and array.dtype.kind == "f" and not np.isfinite(array).all():
                    raise ValueError(f"artifact array {entry.filename[:-4]} must contain finite values")
                arrays[entry.filename[:-4]] = array
    return arrays


def load_npy_array(path: Path) -> np.ndarray:
    """Load a plain NPY with the same preallocation and byte checks."""
    path = Path(path)
    if path.suffix.lower() != ".npy" or path.is_symlink():
        raise ValueError("artifact must be a non-symlink NPY")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        if size > MAX_EXPANDED_BYTES:
            raise ValueError("artifact exceeds expanded byte limit")
        _npy_header(handle, size)
        handle.seek(0)
        raw = handle.read(size + 1)
    if len(raw) != size:
        raise ValueError("artifact changed while reading")
    _npy_header(io.BytesIO(raw), len(raw))
    array = np.load(io.BytesIO(raw), allow_pickle=False, max_header_size=16_384)
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        raise ValueError("artifact arrays must contain finite values")
    return array


def save_npz_arrays(path: Path, arrays: dict) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".npz" or path.is_symlink():
        raise ValueError("artifact destination must be a non-symlink NPZ")
    normalized = {key: np.asarray(value) for key, value in arrays.items()}
    for key, array in normalized.items():
        if not key or "/" in key or "\\" in key or array.dtype.kind not in "biufUS":
            raise ValueError(f"artifact array {key} must use numeric or string dtype")
        if array.dtype.kind == "f" and not np.isfinite(array).all():
            raise ValueError(f"artifact array {key} must contain finite values")
    if sum(array.nbytes for array in normalized.values()) > MAX_EXPANDED_BYTES:
        raise ValueError("artifact exceeds expanded byte limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".npz")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(handle, **normalized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def save_sparse_cache(path: Path, adjacency: sp.spmatrix, stats: dict | None = None) -> Path:
    matrix = adjacency.tocsr(copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    payload = {"format": np.asarray("csr"), "shape": np.asarray(matrix.shape, dtype=np.int64),
               "data": matrix.data, "indices": matrix.indices, "indptr": matrix.indptr,
               "stats_json": np.asarray(json.dumps(stats or {}, allow_nan=False))}
    # Validate the same contract before writing.
    _sparse_payload(payload)
    return save_npz_arrays(path, payload)


def _sparse_payload(payload: dict) -> tuple[sp.csr_matrix, dict]:
    required = {"format", "shape", "data", "indices", "indptr"}
    format_value = payload.get("format", np.asarray("")).item()
    if isinstance(format_value, bytes):
        format_value = format_value.decode("ascii")
    if required - set(payload) or format_value != "csr":
        raise ValueError("adjacency artifact must contain CSR arrays")
    shape, values, indices, indptr = (payload[key] for key in ("shape", "data", "indices", "indptr"))
    if shape.shape != (2,) or shape.dtype.kind not in "iu":
        raise ValueError("adjacency shape must contain two integers")
    n = int(shape[0])
    if n < 0 or n > MAX_NODES or shape[1] != n:
        raise ValueError("adjacency must be square within node limit")
    if values.ndim != 1 or values.dtype.kind not in "biuf" or len(values) > MAX_EDGES:
        raise ValueError("adjacency values must be bounded numeric data")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("adjacency values must be finite and nonnegative")
    if indices.shape != values.shape or indices.dtype.kind not in "iu" or np.any(indices < 0) or np.any(indices >= n):
        raise ValueError("adjacency indices must reference the node domain")
    if indptr.shape != (n + 1,) or indptr.dtype.kind not in "iu" or indptr[0] != 0 or indptr[-1] != len(values) or np.any(indptr[1:] < indptr[:-1]):
        raise ValueError("adjacency CSR row pointers are invalid")
    encoded = payload.get("stats_json", np.asarray("{}"))
    if encoded.ndim != 0 or encoded.dtype.kind not in "US" or len(str(encoded.item())) > 65536:
        raise ValueError("adjacency metadata must be bounded JSON")
    stats = json.loads(str(encoded.item()))
    if not isinstance(stats, dict):
        raise ValueError("adjacency metadata must be a JSON object")
    return sp.csr_matrix((values, indices, indptr), shape=(n, n)), stats


def load_sparse_cache(path: Path) -> tuple[sp.csr_matrix, dict]:
    return _sparse_payload(load_npz_arrays(path))
