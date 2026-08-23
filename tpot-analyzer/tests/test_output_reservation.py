from __future__ import annotations

import pytest

from src.artifacts.output_reservation import reserve_new_outputs


def test_reserves_new_output_bundle_and_creates_parent(tmp_path):
    output = tmp_path / "generation" / "bundle.npz"
    lock = tmp_path / "generation" / "bundle.build.lock"

    with reserve_new_outputs([output], lock):
        assert lock.exists()
        assert output.parent.is_dir()
        with pytest.raises(FileExistsError, match="already active"):
            with reserve_new_outputs([output], lock):
                pass

    assert not lock.exists()


def test_refuses_existing_output_and_releases_owned_lock(tmp_path):
    output = tmp_path / "bundle.npz"
    output.write_bytes(b"existing")
    lock = tmp_path / "bundle.build.lock"

    with pytest.raises(FileExistsError, match="Refusing non-atomic overwrite"):
        with reserve_new_outputs([output], lock):
            pass

    assert not lock.exists()
