"""Test intent: safe CSR round-trip, rejection of pickle/object NPZ,
malformed CSR and archive expansion limits, and string-only saved identities.
"""
import pickle

import numpy as np
import pytest
import scipy.sparse as sp

from src.artifacts.safe_io import load_npz_arrays, load_sparse_cache, save_sparse_cache
from src.data.adjacency import load_adjacency_cache


def test_sparse_round_trip_preserves_weights_and_metadata(tmp_path):
    path = tmp_path / "adjacency.npz"
    matrix = sp.csr_matrix([[0., 1.5], [2., 0.]])
    save_sparse_cache(path, matrix, {"mode": "off", "weighted_edges": 2})
    result, metadata = load_sparse_cache(path)
    assert (result != matrix).nnz == 0
    assert metadata == {"mode": "off", "weighted_edges": 2}
    assert (load_adjacency_cache(path) != matrix).nnz == 0


def test_legacy_pickle_rejected_without_deserialization(tmp_path):
    path = tmp_path / "adjacency.pkl"
    path.write_bytes(pickle.dumps(sp.eye(2, format="csr")))
    with pytest.raises(ValueError, match="regenerate legacy pickle"):
        load_adjacency_cache(path)


def test_object_dtype_rejected_even_if_unused(tmp_path):
    path = tmp_path / "spectral.npz"
    np.savez(path, node_ids=np.array(["a"], dtype=object), embedding=np.ones((1, 1)))
    with pytest.raises(ValueError, match="Object arrays"):
        load_npz_arrays(path)


def test_malformed_csr_never_constructed(tmp_path):
    path = tmp_path / "bad.npz"
    np.savez(path, format=np.asarray("csr"), shape=np.array([2, 2]), data=np.array([1.]),
             indices=np.array([100]), indptr=np.array([0, 0, 1]))
    with pytest.raises(ValueError, match="node domain"):
        load_sparse_cache(path)


def test_symlink_is_rejected(tmp_path):
    path = tmp_path / "valid.npz"
    save_sparse_cache(path, sp.eye(2, format="csr"))
    link = tmp_path / "linked.npz"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="non-symlink"):
        load_sparse_cache(link)


def test_expanded_byte_limit_checked_before_array_loading(tmp_path, monkeypatch):
    from src.artifacts import safe_io
    path = tmp_path / "big.npz"
    np.savez_compressed(path, data=np.zeros(1024))
    monkeypatch.setattr(safe_io, "MAX_EXPANDED_BYTES", 32)
    with pytest.raises(ValueError, match="expanded byte"):
        load_npz_arrays(path)


def test_standard_scipy_numeric_npz_is_supported(tmp_path):
    path = tmp_path / "scipy.npz"
    matrix = sp.eye(2, format="csr")
    sp.save_npz(path, matrix)
    loaded, metadata = load_sparse_cache(path)
    assert (loaded != matrix).nnz == 0
    assert metadata == {}


def test_unsigned_decreasing_csr_pointers_are_rejected(tmp_path):
    path = tmp_path / "bad-pointers.npz"
    np.savez(path, format=np.asarray("csr"), shape=np.array([3, 3]), data=np.array([1.]),
             indices=np.array([0]), indptr=np.array([0, 1, 0, 1], dtype=np.uint32))
    with pytest.raises(ValueError, match="row pointers"):
        load_sparse_cache(path)


def test_forged_npy_allocation_is_rejected_before_numpy_allocation(tmp_path, monkeypatch):
    import struct
    import zipfile
    import numpy.lib.format
    header = repr({"descr": "<f8", "fortran_order": False, "shape": (10**12,)}).encode()
    header += b" " * ((64 - (10 + len(header) + 1) % 64) % 64) + b"\n"
    raw = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header
    path = tmp_path / "forged.npz"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.npy", raw)
    def allocation_forbidden(*args, **kwargs):
        raise AssertionError("NumPy allocation was reached before header validation")
    monkeypatch.setattr(numpy.lib.format.numpy, "ndarray", allocation_forbidden)
    with pytest.raises(ValueError, match="shape|allocation"):
        load_npz_arrays(path)


def test_truncated_npy_data_is_rejected_before_loading(tmp_path, monkeypatch):
    import struct
    import zipfile
    header = repr({"descr": "<f8", "fortran_order": False, "shape": (10,)}).encode() + b"\n"
    path = tmp_path / "truncated.npz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data.npy", b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header)
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: pytest.fail("NumPy load must not run"))
    with pytest.raises(ValueError, match="byte length mismatch"):
        load_npz_arrays(path)


@pytest.mark.parametrize("descr", ["<U0", "|S0"])
def test_zero_width_string_header_is_rejected_before_allocation(tmp_path, monkeypatch, descr):
    import struct
    import zipfile
    import numpy.lib.format
    header = repr({"descr": descr, "fortran_order": False, "shape": (1_000_000_000,)}).encode() + b"\n"
    path = tmp_path / "zero-width.npz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("node_ids.npy", b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header)
    monkeypatch.setattr(numpy.lib.format.numpy, "ndarray", lambda *args, **kwargs: pytest.fail("Allocation must not run"))
    with pytest.raises(ValueError, match="shape/dtype"):
        load_npz_arrays(path)
