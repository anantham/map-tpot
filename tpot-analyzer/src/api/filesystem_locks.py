"""Private, no-follow POSIX runtime lock files without reading analyst data."""
from __future__ import annotations

import fcntl
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path


class UnsafeRuntimePath(OSError):
    """Runtime coordination is disabled when filesystem integrity is uncertain."""


def _check_directory(metadata, *, private=False):
    mode = stat.S_IMODE(metadata.st_mode)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise UnsafeRuntimePath("runtime directory must be owned by the current user")
    if mode & 0o022 or (private and mode != 0o700):
        raise UnsafeRuntimePath("runtime directory permissions are unsafe")


def _reject_symlink_components(path):
    for component in (path, *path.parents):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafeRuntimePath("runtime paths must not contain symlinks")


@contextmanager
def private_runtime_directory(root, *, create=False):
    """Pin an owned, non-writable-to-others root and a private coordination dir."""
    path = Path(root).expanduser().absolute()
    _reject_symlink_components(path)
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        _reject_symlink_components(path)
    root_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    runtime_fd = None
    try:
        _check_directory(os.fstat(root_fd))
        try:
            os.mkdir(".tpot-security-runtime", 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        runtime_fd = os.open(".tpot-security-runtime", os.O_RDONLY | os.O_DIRECTORY |
                             os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
        _check_directory(os.fstat(runtime_fd), private=True)
        yield root_fd, runtime_fd
    finally:
        if runtime_fd is not None:
            os.close(runtime_fd)
        os.close(root_fd)


def check_private_file(metadata):
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
        raise UnsafeRuntimePath("runtime file must be a private, owned, single-link regular file")


def open_private_file(directory_fd, name):
    if not name or "/" in name or name in {".", ".."}:
        raise ValueError("runtime filename must be a basename")
    # Open existing files without O_CREAT; exclusive creation distinguishes a
    # competing creator from a disappearing/unsafe directory. The macOS process
    # regression observed ENOENT during simultaneous O_CREAT|O_NOFOLLOW opens.
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    for attempt in range(3):
        try:
            fd = os.open(name, flags, dir_fd=directory_fd)
            break
        except FileNotFoundError:
            try:
                fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600,
                             dir_fd=directory_fd)
                break
            except (FileExistsError, FileNotFoundError):
                if attempt == 2:
                    raise
    try:
        check_private_file(os.fstat(fd))
    except BaseException:
        os.close(fd)
        raise
    return fd


def try_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def bounded_lock(fd, timeout_seconds=.5):
    deadline = time.monotonic() + timeout_seconds
    while not try_lock(fd):
        if time.monotonic() >= deadline:
            raise BlockingIOError("runtime lock busy; retry later")
        time.sleep(.005)


class FileLease:
    def __init__(self, fd):
        self._fd = fd

    def release(self):
        fd, self._fd = self._fd, None
        if fd is not None:
            os.close(fd)  # Closing the descriptor releases flock, including after crashes.
