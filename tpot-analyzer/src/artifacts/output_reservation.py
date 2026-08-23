"""Cooperating-writer reservation for new, unpublished artifact outputs."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def reserve_new_outputs(output_paths, lock_path):
    """Reserve absent paths for one writer; this is not atomic publication."""
    paths = [Path(path) for path in output_paths]
    lock_path = Path(lock_path)
    for parent in {path.parent for path in [*paths, lock_path]}:
        parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise FileExistsError(
            f"Artifact writer already active or stale lock remains: {lock_path}"
        ) from exc
    os.close(lock_fd)
    try:
        existing = [path for path in paths if path.exists()]
        if existing:
            raise FileExistsError(
                "Refusing non-atomic overwrite of existing artifact outputs; "
                f"choose a new generation path. Existing={existing}"
            )
        yield
    finally:
        lock_path.unlink(missing_ok=True)
