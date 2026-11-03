"""Security intent: locks must coordinate independent OS processes and reject
unsafe filesystem entries; unsupervised graph endpoints must never execute work.
Fixtures contain no personal data and subprocesses never access a network.
"""
import multiprocessing as mp
from pathlib import Path

import pytest

from src.api.security_policy import WorkloadGate
from src.api.server import create_app


def _probe_gate(path, queue):
    gate = WorkloadGate()
    acquired = gate.acquire()
    queue.put(acquired)
    if acquired:
        gate.release()


def test_global_gate_blocks_an_independent_process(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    gate = WorkloadGate()
    assert gate.acquire()
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    worker = ctx.Process(target=_probe_gate, args=(str(tmp_path), queue))
    worker.start()
    try:
        assert queue.get(timeout=10) is False
        worker.join(10)
        assert worker.exitcode == 0
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join()
        gate.release()
    next_gate = WorkloadGate()
    assert next_gate.acquire()
    next_gate.release()


@pytest.mark.parametrize("path", ["/api/analysis/run", "/api/metrics/compute"])
def test_unsupervised_whole_graph_http_work_is_disabled(temp_snapshot_dir, monkeypatch, path):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "fixture")
    monkeypatch.setattr("src.api.server.init_cluster_routes", lambda _: None)
    monkeypatch.setattr("src.api.routes.graph.build_graph", lambda **_: pytest.fail("graph work executed"))
    app = create_app({"TESTING": True})
    response = app.test_client().post(path, headers={"X-TPOT-Curator-Token": "fixture"}, json={"seeds": []})
    assert response.status_code == 503
    assert "bounded" in response.get_json()["error"]
    assert not app.config["ANALYSIS_MANAGER"].is_running()


@pytest.mark.parametrize("attack", ["root_symlink", "root_writable", "runtime_symlink", "runtime_mode", "slot_symlink", "slot_hardlink", "slot_mode"])
def test_gate_rejects_unsafe_filesystem_entries(tmp_path, attack):
    root = tmp_path / "snapshot"
    root.mkdir()
    runtime = root / ".tpot-security-runtime"
    runtime.mkdir(mode=0o700)
    target = tmp_path / "unchanged.txt"
    target.write_text("synthetic sentinel")
    target.chmod(0o600)
    if attack == "root_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    elif attack == "root_writable":
        root.chmod(0o777)
    elif attack == "runtime_symlink":
        runtime.rmdir()
        runtime.symlink_to(tmp_path, target_is_directory=True)
    elif attack == "runtime_mode":
        runtime.chmod(0o755)
    elif attack == "slot_symlink":
        (runtime / "workload-slot-0").symlink_to(target)
    elif attack == "slot_hardlink":
        import os
        os.link(target, runtime / "workload-slot-0")
    elif attack == "slot_mode":
        slot = runtime / "workload-slot-0"
        slot.write_text("")
        slot.chmod(0o644)
    with pytest.raises(OSError):
        WorkloadGate(lock_root=root).acquire()
    assert target.read_text() == "synthetic sentinel"


def test_gate_rejects_inconsistent_worker_capacity(tmp_path):
    first = WorkloadGate(1, lock_root=tmp_path)
    assert first.acquire()
    first.release()
    with pytest.raises(OSError, match="disagree"):
        WorkloadGate(2, lock_root=tmp_path).acquire()


def _write_logs(path, queue, count):
    from src.api.bounded_logs import append_private_log
    try:
        for i in range(count):
            append_private_log(path, f"synthetic-{i}-" + "x" * 90, max_bytes=400, backups=2)
        queue.put(None)
    except Exception:
        import traceback
        queue.put(traceback.format_exc())


@pytest.mark.parametrize("attempt", range(5))
def test_log_rotation_has_a_shared_disk_ceiling_across_processes(tmp_path, attempt):
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    path = tmp_path / "frontend.log"
    workers = [ctx.Process(target=_write_logs, args=(str(path), queue, 30)) for _ in range(3)]
    for worker in workers:
        worker.start()
    try:
        results = [queue.get(timeout=15) for _ in workers]
        assert results == [None, None, None], "\n".join(result for result in results if result)
        for worker in workers:
            worker.join(10)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
    files = list(tmp_path.glob("frontend.log*"))
    assert len(files) == 3
    assert sum(file.stat().st_size for file in files) <= 1200
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in files)


def test_log_rotation_rejects_symlink_and_preserves_target(tmp_path):
    from src.api.bounded_logs import append_private_log
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("preserve")
    sentinel.chmod(0o600)
    path = tmp_path / "frontend.log"
    path.symlink_to(sentinel)
    with pytest.raises(OSError):
        append_private_log(path, "rejected", max_bytes=400, backups=2)
    assert sentinel.read_text() == "preserve"


def _hold_gate(queue):
    gate = WorkloadGate()
    queue.put(gate.acquire())
    import time
    time.sleep(30)


def test_process_exit_releases_global_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    worker = ctx.Process(target=_hold_gate, args=(queue,))
    worker.start()
    try:
        assert queue.get(timeout=10) is True
        assert not WorkloadGate().acquire()
    finally:
        worker.terminate()
        worker.join(10)
    next_gate = WorkloadGate()
    assert next_gate.acquire()
    next_gate.release()


def test_gate_rejects_wrong_owner_metadata(tmp_path, monkeypatch):
    import src.api.filesystem_locks as module
    from types import SimpleNamespace
    inode = tmp_path.stat().st_ino
    original = module.os.fstat
    def wrong_owner(fd):
        metadata = original(fd)
        if metadata.st_ino == inode:
            return SimpleNamespace(st_mode=metadata.st_mode, st_uid=metadata.st_uid + 1)
        return metadata
    monkeypatch.setattr(module.os, "fstat", wrong_owner)
    with pytest.raises(OSError, match="owned"):
        WorkloadGate(lock_root=tmp_path).acquire()


def test_failed_thread_start_releases_global_lease(tmp_path, monkeypatch):
    import threading
    from src.api.services.analysis_manager import AnalysisManager
    gate = WorkloadGate(lock_root=tmp_path)
    manager = AnalysisManager(workload_gate=gate)
    def fail(_):
        raise RuntimeError("synthetic startup failure")
    monkeypatch.setattr(threading.Thread, "start", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        manager.start_analysis(lambda _: None)
    assert manager.get_status()["status"] == "failed"
    assert gate.acquire()
    gate.release()


def test_private_file_creation_retries_a_competing_creator(tmp_path, monkeypatch):
    import os
    import src.api.filesystem_locks as module
    with module.private_runtime_directory(tmp_path) as (_, directory_fd):
        fd = module.open_private_file(directory_fd, "fixture-lock")
        os.close(fd)
        original = module.os.open
        calls = []
        def racing(name, flags, *args, **kwargs):
            calls.append(flags)
            if len(calls) == 1:
                raise FileNotFoundError("synthetic lookup race")
            return original(name, flags, *args, **kwargs)
        monkeypatch.setattr(module.os, "open", racing)
        fd = module.open_private_file(directory_fd, "fixture-lock")
        os.close(fd)
        assert len(calls) == 3
        assert calls[1] & os.O_EXCL


def test_private_file_creation_race_retry_is_bounded(tmp_path, monkeypatch):
    import src.api.filesystem_locks as module
    with module.private_runtime_directory(tmp_path) as (_, directory_fd):
        calls = []
        def absent(*args, **kwargs):
            calls.append(args)
            raise FileNotFoundError("synthetic missing directory")
        monkeypatch.setattr(module.os, "open", absent)
        with pytest.raises(FileNotFoundError):
            module.open_private_file(directory_fd, "fixture-lock")
        assert len(calls) == 6
