"""Finite log rotation serialized across processes with private no-follow files."""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from src.api.filesystem_locks import (
    bounded_lock, check_private_file, open_private_file, private_runtime_directory,
)


def append_private_log(path, line, *, max_bytes, backups):
    path = Path(path).expanduser().absolute()
    encoded = (line + "\n").encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("log entry exceeds file quota")
    with private_runtime_directory(path.parent, create=True) as (root_fd, runtime_fd):
        lock_name = "log-" + hashlib.sha256(path.name.encode()).hexdigest()[:24]
        lock_fd = open_private_file(runtime_fd, lock_name)
        try:
            bounded_lock(lock_fd)
            # Check all existing retention entries before any rename/delete.
            for name in [path.name, *(f"{path.name}.{i}" for i in range(1, backups + 1))]:
                try:
                    metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                check_private_file(metadata)
                if metadata.st_size > max_bytes:
                    raise OSError("existing log exceeds quota; archive it before resuming logging")
            fd = open_private_file(root_fd, path.name)
            try:
                if os.fstat(fd).st_size + len(encoded) > max_bytes:
                    os.close(fd)
                    fd = None
                    if backups:
                        try:
                            os.unlink(f"{path.name}.{backups}", dir_fd=root_fd)
                        except FileNotFoundError:
                            pass
                        for number in range(backups - 1, 0, -1):
                            try:
                                os.rename(f"{path.name}.{number}", f"{path.name}.{number + 1}",
                                          src_dir_fd=root_fd, dst_dir_fd=root_fd)
                            except FileNotFoundError:
                                pass
                        os.rename(path.name, f"{path.name}.1", src_dir_fd=root_fd, dst_dir_fd=root_fd)
                    else:
                        os.unlink(path.name, dir_fd=root_fd)
                    fd = open_private_file(root_fd, path.name)
                os.lseek(fd, 0, os.SEEK_END)
                remaining = memoryview(encoded)
                while remaining:
                    written = os.write(fd, remaining)
                    if written <= 0:
                        raise OSError("log write made no progress")
                    remaining = remaining[written:]
            finally:
                if fd is not None:
                    os.close(fd)
        finally:
            os.close(lock_fd)


class PrivateRotatingHandler(logging.Handler):
    """Use the same bounded cross-process writer for server diagnostics."""

    def __init__(self, path, *, max_bytes, backups, max_entry_bytes=16 * 1024):
        super().__init__()
        self.baseFilename = str(Path(path).absolute())
        self.max_bytes, self.backups = max_bytes, backups
        self.max_entry_bytes = max_entry_bytes

    def emit(self, record):
        try:
            line = self.format(record)
            if len(line.encode("utf-8")) > self.max_entry_bytes:
                line = line.encode("utf-8")[:self.max_entry_bytes - 32].decode("utf-8", errors="ignore") + " [log entry truncated]"
            append_private_log(self.baseFilename, line, max_bytes=self.max_bytes, backups=self.backups)
        except Exception:
            self.handleError(record)
