import subprocess
import sys
import time

import pytest

from runsentry.execution import RunSpec, execute_command
import runsentry.observation as observation
from runsentry.observation import ProcessResourceObserver, root_create_time_for_pid

try:
    import psutil
except ModuleNotFoundError:
    psutil = None

requires_psutil = pytest.mark.skipif(psutil is None, reason="psutil is required")


@requires_psutil
def test_root_process_observation_and_rss() -> None:
    process = _start_python("import time; time.sleep(3)")
    try:
        observer = _observer_for_process(process)
        snapshot = _wait_for(lambda: observer.sample().root_observation.alive)
        assert snapshot.root_identity.pid == process.pid
        assert snapshot.root_observation.status is not None
        assert snapshot.root_observation.rss_bytes is None or snapshot.root_observation.rss_bytes >= 0
    finally:
        _terminate_process(process)


@requires_psutil
def test_cpu_first_sample_is_unknown_then_defensible() -> None:
    process = _start_python("import time; end=time.time()+2\nwhile time.time()<end: pass")
    try:
        observer = _observer_for_process(process)
        first = observer.sample()
        second = _wait_for(lambda: observer.sample())
        assert first.root_observation.cpu_percent is None
        assert second.root_observation.cpu_percent is None or second.root_observation.cpu_percent >= 0.0
    finally:
        _terminate_process(process)


@requires_psutil
def test_child_discovery_and_recursive_descendants() -> None:
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', "
        "\"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)']); time.sleep(3)\"])\n"
        "time.sleep(3)\n"
    )
    process = _start_python(script)
    try:
        observer = _observer_for_process(process)
        snapshot = _wait_for(
            lambda: observer.sample()
            if observer.sample().observable_descendant_count >= 2
            else None,
            timeout_s=5.0,
        )
        assert snapshot.observable_descendant_count >= 2
        assert len(snapshot.known_descendants) >= 2
    finally:
        _terminate_tree(process)


@requires_psutil
def test_descendant_registry_retains_observed_outliving_child() -> None:
    script = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'])\n"
        "print('ready', flush=True)\n"
        "time.sleep(0.5)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
        observer = _observer_for_process(process)
        observed = _wait_for(
            lambda: observer.sample()
            if observer.sample().observable_descendant_count >= 1
            else None,
            timeout_s=2.0,
        )
        assert observed.known_descendants
        process.wait(timeout=3)
        after_root_exit = observer.sample()
        assert after_root_exit.known_descendants == observed.known_descendants
    finally:
        _terminate_tree(process)


@requires_psutil
def test_short_lived_child_race_does_not_crash() -> None:
    script = (
        "import subprocess, sys, time\n"
        "for _ in range(50):\n"
        "    subprocess.Popen([sys.executable, '-c', 'pass'])\n"
        "time.sleep(1)\n"
    )
    process = _start_python(script)
    try:
        observer = _observer_for_process(process)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and process.poll() is None:
            snapshot = observer.sample()
            assert snapshot.unavailable_reasons is not None
            time.sleep(0.05)
    finally:
        _terminate_tree(process)


@requires_psutil
def test_process_disappears_during_sample_degrades_gracefully() -> None:
    process = _start_python("pass")
    observer = _observer_for_process(process)
    process.wait(timeout=3)
    snapshot = observer.sample()
    assert not snapshot.root_observation.alive
    assert "root_not_observable" in snapshot.unavailable_reasons


@requires_psutil
def test_tree_rss_aggregation_and_completeness_metadata() -> None:
    process = _start_python("import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)']); time.sleep(3)")
    try:
        observer = _observer_for_process(process)
        snapshot = _wait_for(
            lambda: observer.sample()
            if observer.sample().observable_descendant_count >= 1
            else None,
            timeout_s=5.0,
        )
        assert snapshot.tree_rss_bytes is None or snapshot.tree_rss_bytes >= 0
        assert isinstance(snapshot.tree_rss_partial, bool)
        assert isinstance(snapshot.observation_complete, bool)
    finally:
        _terminate_tree(process)


@requires_psutil
def test_system_memory_and_swap_snapshots_are_factual() -> None:
    process = _start_python("import time; time.sleep(1)")
    try:
        snapshot = _observer_for_process(process).sample()
        assert snapshot.system_memory.total_bytes is None or snapshot.system_memory.total_bytes >= 0
        assert snapshot.system_memory.available_bytes is None or snapshot.system_memory.available_bytes >= 0
        assert snapshot.system_memory.used_bytes is None or snapshot.system_memory.used_bytes >= 0
        assert snapshot.system_memory.percent is None or snapshot.system_memory.percent >= 0.0
        assert snapshot.swap.total_bytes is None or snapshot.swap.total_bytes >= 0
        assert snapshot.swap.used_bytes is None or snapshot.swap.used_bytes >= 0
        assert snapshot.swap.free_bytes is None or snapshot.swap.free_bytes >= 0
        assert snapshot.swap.percent is None or snapshot.swap.percent >= 0.0
    finally:
        _terminate_process(process)


@requires_psutil
def test_output_coexists_with_resource_sampling() -> None:
    script = (
        "import os, sys, threading, time\n"
        "payload_size = 65536 * 10\n"
        "def write_all(fd, byte):\n"
        "    chunk = byte * 8192\n"
        "    remaining = payload_size\n"
        "    while remaining:\n"
        "        n = min(len(chunk), remaining)\n"
        "        os.write(fd, chunk[:n])\n"
        "        remaining -= n\n"
        "threads = [threading.Thread(target=write_all, args=(sys.stdout.fileno(), b'o')), threading.Thread(target=write_all, args=(sys.stderr.fileno(), b'e'))]\n"
        "[t.start() for t in threads]\n"
        "time.sleep(1.2)\n"
        "[t.join() for t in threads]\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "runsentry", "run", "--interval", "1", "--", sys.executable, "-c", script],
        check=False,
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 0
    assert result.stdout == b"o" * (65536 * 10)
    assert result.stderr == b"e" * (65536 * 10)


@requires_psutil
def test_nonzero_exit_semantics_remain_intact() -> None:
    result = execute_command(RunSpec(name="nonzero", argv=[sys.executable, "-c", "raise SystemExit(7)"]))
    assert result.exit_code == 7
    assert result.latest_resource_snapshot is not None


@requires_psutil
def test_production_execution_retains_only_latest_snapshot() -> None:
    result = execute_command(
        RunSpec(
            name="bounded",
            argv=[sys.executable, "-c", "import time; time.sleep(1.2)"],
            sample_interval_s=1.0,
        )
    )
    assert result.latest_resource_snapshot is not None
    assert not hasattr(result, "snapshots")


def test_psutil_unavailable_snapshot_degrades_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr(observation, "psutil", None)
    observer = ProcessResourceObserver(
        root_pid=123456,
        launch_monotonic_s=time.monotonic(),
        root_create_time_epoch_s=None,
    )
    snapshot = observer.sample()
    assert snapshot.unavailable_reasons == ("psutil_unavailable",)
    assert not snapshot.observation_complete
    assert snapshot.system_memory.unavailable
    assert snapshot.swap.unavailable


def _start_python(script: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", script])


def _observer_for_process(process: subprocess.Popen) -> ProcessResourceObserver:
    return ProcessResourceObserver(
        root_pid=process.pid,
        launch_monotonic_s=time.monotonic(),
        root_create_time_epoch_s=root_create_time_for_pid(process.pid),
    )


def _wait_for(callback, timeout_s: float = 4.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = callback()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition was not met before timeout")


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def _terminate_tree(process: subprocess.Popen) -> None:
    try:
        root = psutil.Process(process.pid)
        children = root.children(recursive=True)
    except psutil.Error:
        children = []
    _terminate_process(process)
    for child in children:
        try:
            child.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        try:
            child.kill()
        except psutil.Error:
            pass
