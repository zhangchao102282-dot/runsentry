import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from runsentry.execution import EXIT_SIGINT, RunSpec, execute_command
from runsentry.watch import PathObserver


def test_no_watch_path_remains_allowed() -> None:
    result = execute_command(RunSpec(name="no-watch", argv=[sys.executable, "-c", "pass"]))
    assert result.exit_code == 0
    assert result.latest_watched_paths == ()


def test_watch_before_boundary_is_runsentry_option(tmp_path) -> None:
    argv_path = tmp_path / "argv.json"
    watched = tmp_path / "watched.txt"
    watched.write_text("x")
    script = (
        "import json, pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--watch",
            str(watched),
            "--",
            sys.executable,
            "-c",
            script,
            str(argv_path),
            "child",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(argv_path.read_text()) == ["child"]


def test_watch_after_boundary_belongs_to_child_argv(tmp_path) -> None:
    argv_path = tmp_path / "argv.json"
    script = (
        "import json, pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--",
            sys.executable,
            "-c",
            script,
            str(argv_path),
            "--watch",
            "child-value",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(argv_path.read_text()) == ["--watch", "child-value"]


def test_existing_regular_file_observes_size_mtime_and_disk(tmp_path) -> None:
    watched = tmp_path / "file.txt"
    watched.write_bytes(b"abc")
    observation = PathObserver([str(watched)]).sample()[0]
    assert observation.exists
    assert observation.kind == "file"
    assert observation.size_bytes == 3
    assert observation.latest_mtime_epoch_s is not None
    assert observation.device_id is not None
    assert observation.inode is not None
    assert observation.disk_usage is not None
    assert observation.disk_usage.total_bytes is not None
    assert observation.disk_usage.used_bytes is not None
    assert observation.disk_usage.free_bytes is not None


def test_watched_regular_file_growth_records_positive_delta(tmp_path) -> None:
    watched = tmp_path / "grow.txt"
    watched.write_bytes(b"a")
    observer = PathObserver([str(watched)])
    observer.sample()
    watched.write_bytes(b"abcdef")
    observation = observer.sample()[0]
    assert observation.size_bytes == 6
    assert observation.size_delta_bytes == 5
    assert observation.changed_since_previous_sample


def test_watched_file_grows_during_execution(tmp_path) -> None:
    watched = tmp_path / "during-run.txt"
    watched.write_text("a")
    script = (
        "import pathlib, sys, time; "
        "path = pathlib.Path(sys.argv[1]); "
        "time.sleep(1.2); "
        "path.write_text('abcdef')"
    )
    result = execute_command(
        RunSpec(
            name="file-growth",
            argv=[sys.executable, "-c", script, str(watched)],
            sample_interval_s=1.0,
            watch_paths=[str(watched)],
        )
    )
    observation = result.latest_watched_paths[0]
    assert result.exit_code == 0
    assert observation.size_bytes == 6
    assert observation.size_delta_bytes is not None
    assert observation.size_delta_bytes > 0


def test_missing_path_appears_later_as_file(tmp_path) -> None:
    watched = tmp_path / "appears.txt"
    observer = PathObserver([str(watched)])
    missing = observer.sample()[0]
    assert missing.kind == "missing"
    watched.write_text("new")
    appeared = observer.sample()[0]
    assert appeared.exists
    assert appeared.kind == "file"
    assert appeared.changed_since_previous_sample
    assert appeared.size_bytes == 3


def test_watched_file_deleted_during_run_is_missing_gracefully(tmp_path) -> None:
    watched = tmp_path / "delete.txt"
    watched.write_text("old")
    observer = PathObserver([str(watched)])
    observer.sample()
    watched.unlink()
    deleted = observer.sample()[0]
    assert not deleted.exists
    assert deleted.kind == "missing"
    assert deleted.changed_since_previous_sample


def test_watched_file_replacement_detects_identity_change(tmp_path) -> None:
    watched = tmp_path / "replace.txt"
    watched.write_text("old")
    observer = PathObserver([str(watched)])
    first = observer.sample()[0]
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("newer")
    replacement.replace(watched)
    second = observer.sample()[0]
    if first.device_id is None or first.inode is None or second.device_id is None or second.inode is None:
        assert second.replaced_since_previous_sample is None
    else:
        assert second.replaced_since_previous_sample is True
    assert second.changed_since_previous_sample


def test_watched_directory_aggregate_size_and_file_count(tmp_path) -> None:
    watched = tmp_path / "dir"
    nested = watched / "nested"
    nested.mkdir(parents=True)
    (watched / "a.txt").write_bytes(b"abc")
    (nested / "b.txt").write_bytes(b"de")
    observation = PathObserver([str(watched)]).sample()[0]
    assert observation.kind == "directory"
    assert observation.aggregate_size_bytes == 5
    assert observation.file_count == 2
    assert observation.latest_mtime_epoch_s is not None


def test_directory_growth_records_delta_and_file_count_change(tmp_path) -> None:
    watched = tmp_path / "dir"
    watched.mkdir()
    (watched / "a.txt").write_bytes(b"a")
    observer = PathObserver([str(watched)])
    observer.sample()
    (watched / "b.txt").write_bytes(b"bcde")
    observation = observer.sample()[0]
    assert observation.aggregate_size_bytes == 5
    assert observation.file_count == 2
    assert observation.size_delta_bytes == 4
    assert observation.changed_since_previous_sample


def test_directory_race_does_not_crash(monkeypatch, tmp_path) -> None:
    watched = tmp_path / "dir"
    watched.mkdir()
    (watched / "a.txt").write_text("x")
    original_scandir = os.scandir

    def racing_scandir(path):
        if Path(path) == watched:
            raise FileNotFoundError(path)
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", racing_scandir)
    observation = PathObserver([str(watched)]).sample()[0]
    assert observation.kind == "directory"
    assert observation.observation_partial
    assert observation.unavailable_reason == "directory_race"


def test_inaccessible_path_records_reason(monkeypatch, tmp_path) -> None:
    watched = tmp_path / "inaccessible.txt"
    watched.write_text("x")
    original_stat = Path.stat

    def denied_stat(self, *args, **kwargs):
        if self == watched:
            raise PermissionError("denied")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied_stat)
    observation = PathObserver([str(watched)]).sample()[0]
    assert observation.kind == "inaccessible"
    assert observation.observation_partial
    assert observation.unavailable_reason == "permission_denied"


def test_disk_usage_for_missing_path_uses_existing_parent(tmp_path) -> None:
    watched = tmp_path / "missing.txt"
    observation = PathObserver([str(watched)]).sample()[0]
    assert observation.kind == "missing"
    assert observation.disk_usage is not None
    assert observation.disk_usage.filesystem_path == str(tmp_path)
    assert observation.disk_usage.total_bytes is not None
    assert observation.disk_usage.used_bytes is not None
    assert observation.disk_usage.free_bytes is not None


def test_disk_usage_for_deeply_missing_path_uses_nearest_ancestor(tmp_path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    watched = existing / "a" / "b" / "c.txt"
    observation = PathObserver([str(watched)]).sample()[0]
    assert observation.kind == "missing"
    assert observation.disk_usage is not None
    assert observation.disk_usage.filesystem_path == str(existing)


def test_multiple_watched_paths_are_independent(tmp_path) -> None:
    one = tmp_path / "one.txt"
    two = tmp_path / "two.txt"
    one.write_text("1")
    observer = PathObserver([str(one), str(two)])
    observations = observer.sample()
    assert [item.original_path for item in observations] == [str(one), str(two)]
    assert observations[0].kind == "file"
    assert observations[1].kind == "missing"


def test_output_and_process_sampling_regression_with_watch(tmp_path) -> None:
    watched = tmp_path / "watched.txt"
    watched.write_text("x")
    script = (
        "import os, sys, threading, time\n"
        "payload_size = 65536 * 4\n"
        "def write_all(fd, byte):\n"
        "    chunk = byte * 8192\n"
        "    remaining = payload_size\n"
        "    while remaining:\n"
        "        n = min(len(chunk), remaining)\n"
        "        os.write(fd, chunk[:n])\n"
        "        remaining -= n\n"
        "threads = [threading.Thread(target=write_all, args=(sys.stdout.fileno(), b'o')), threading.Thread(target=write_all, args=(sys.stderr.fileno(), b'e'))]\n"
        "[t.start() for t in threads]\n"
        "time.sleep(1.1)\n"
        "[t.join() for t in threads]\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--interval",
            "1",
            "--watch",
            str(watched),
            "--",
            sys.executable,
            "-c",
            script,
        ],
        check=False,
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 0
    assert result.stdout == b"o" * (65536 * 4)
    assert result.stderr == b"e" * (65536 * 4)


def test_sigint_regression_with_watch(tmp_path) -> None:
    ready_path = tmp_path / "ready.txt"
    watched = tmp_path / "watched.txt"
    watched.write_text("x")
    child = (
        "import pathlib, signal, sys, time\n"
        "def handle(signum, frame):\n"
        "    raise SystemExit(130)\n"
        "signal.signal(signal.SIGINT, handle)\n"
        "pathlib.Path(sys.argv[1]).write_text('ready')\n"
        "time.sleep(30)\n"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--watch",
            str(watched),
            "--",
            sys.executable,
            "-c",
            child,
            str(ready_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        _wait_for_path(ready_path)
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
        stdout, stderr = process.communicate(timeout=8)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    assert process.returncode == EXIT_SIGINT
    assert stdout == ""
    assert "interrupted; child is still running" not in stderr


def test_watched_path_observer_retains_only_latest_and_previous(tmp_path) -> None:
    watched = tmp_path / "file.txt"
    watched.write_text("a")
    observer = PathObserver([str(watched)])
    for value in ("aa", "aaa", "aaaa"):
        watched.write_text(value)
        observer.sample()
    assert len(observer.latest_observations) == 1
    assert len(observer.previous_observations) == 1
    assert not hasattr(observer, "history")
    assert not hasattr(observer, "samples")


def _wait_for_path(path, timeout_s: float = 5.0) -> None:
    deadline_s = time.monotonic() + timeout_s
    while time.monotonic() < deadline_s:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")
