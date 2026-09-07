import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from runsentry.execution import (
    EXIT_COMMAND_NOT_FOUND,
    EXIT_INTERNAL_ERROR,
    EXIT_SIGINT,
    RunSpec,
    execute_command,
)
from runsentry.telemetry import SCHEMA_VERSION, TelemetryWriter, generate_run_id


def test_default_run_creates_telemetry_and_summary_under_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_command(RunSpec(name="default", argv=[sys.executable, "-c", "pass"]))
    run_dir = Path(result.summary_path).parent
    assert run_dir.resolve().parent == tmp_path / ".runsentry" / "runs"
    assert Path(result.telemetry_path).exists()
    assert Path(result.summary_path).exists()


def test_telemetry_jsonl_lines_are_valid_with_required_common_fields(tmp_path) -> None:
    result = _run_with_output_dir(tmp_path, [sys.executable, "-c", "pass"])
    events = _read_events(result.telemetry_path)
    assert events
    for event in events:
        assert event["schema_version"] == SCHEMA_VERSION
        assert event["run_id"] == result.run_id
        assert event["event_type"]
        assert isinstance(event["timestamp_epoch_s"], float)
        assert isinstance(event["elapsed_s"], float)


def test_run_started_contains_launch_configuration(tmp_path) -> None:
    watched = tmp_path / "watched.txt"
    watched.write_text("x")
    result = _run_with_output_dir(
        tmp_path,
        [sys.executable, "-c", "pass"],
        name="started",
        watch_paths=[str(watched)],
    )
    started = _event(result.telemetry_path, "run_started")
    assert started["name"] == "started"
    assert started["argv"] == [sys.executable, "-c", "pass"]
    assert started["cwd"] == os.getcwd()
    assert started["watched_paths"] == [str(watched)]
    assert started["sample_interval_s"] == 1.0
    assert isinstance(started["root_pid"], int)
    assert "root_create_time_epoch_s" in started


def test_long_enough_run_writes_sample_event(tmp_path) -> None:
    result = _run_with_output_dir(
        tmp_path,
        [sys.executable, "-c", "import time; time.sleep(1.2)"],
    )
    samples = _events(result.telemetry_path, "sample")
    assert len(samples) >= 2
    sample = samples[-1]
    assert "process" in sample
    assert "stdout" in sample
    assert "stderr" in sample
    assert "watched_paths" in sample


def test_run_finished_contains_exit_duration_output_and_peaks(tmp_path) -> None:
    result = _run_with_output_dir(
        tmp_path,
        [sys.executable, "-c", "print('done')"],
    )
    finished = _event(result.telemetry_path, "run_finished")
    assert finished["exit_code"] == 0
    assert finished["child_returncode"] == 0
    assert finished["duration_s"] >= 0.0
    assert finished["output_drained"] is True
    assert finished["stdout"]["total_bytes"] >= len("done\n")
    assert "peak_root_rss_bytes" in finished["peaks"]
    assert "peak_tree_rss_bytes" in finished["peaks"]
    assert "max_observable_process_count" in finished["peaks"]
    assert "max_observable_descendant_count" in finished["peaks"]


def test_summary_contains_expected_factual_fields(tmp_path) -> None:
    result = _run_with_output_dir(
        tmp_path,
        [sys.executable, "-c", "import sys; sys.stderr.write('err')"],
        name="summary",
    )
    summary = _read_summary(result.summary_path)
    assert summary["schema_version"] == SCHEMA_VERSION
    assert summary["run_id"] == result.run_id
    assert summary["name"] == "summary"
    assert summary["argv"] == [sys.executable, "-c", "import sys; sys.stderr.write('err')"]
    assert summary["exit_code"] == 0
    assert summary["child_returncode"] == 0
    assert summary["sample_count"] >= 1
    assert summary["stderr"]["total_bytes"] == 3
    assert summary["telemetry_file_path"] == result.telemetry_path
    assert "health_state" in summary["consciously_absent_fields"]
    assert "stall_status" in summary["consciously_absent_fields"]
    assert "oom_risk" in summary["consciously_absent_fields"]
    assert "disk_exhaustion_eta" in summary["consciously_absent_fields"]
    assert "job_eta" in summary["consciously_absent_fields"]


def test_stdout_stderr_content_is_not_stored_but_counts_are(tmp_path) -> None:
    secret_out = "RS_SECRET_STDOUT_CONTENT"
    secret_err = "RS_SECRET_STDERR_CONTENT"
    stdout_codes = [ord(char) for char in secret_out]
    stderr_codes = [ord(char) for char in secret_err]
    result = _run_with_output_dir(
        tmp_path,
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.stdout.write(''.join(map(chr, {stdout_codes!r}))); "
                f"sys.stderr.write(''.join(map(chr, {stderr_codes!r})))"
            ),
        ],
    )
    telemetry_text = Path(result.telemetry_path).read_text()
    summary_text = Path(result.summary_path).read_text()
    assert secret_out not in telemetry_text
    assert secret_err not in telemetry_text
    assert secret_out not in summary_text
    assert secret_err not in summary_text
    summary = _read_summary(result.summary_path)
    assert summary["stdout"]["total_bytes"] == len(secret_out)
    assert summary["stderr"]["total_bytes"] == len(secret_err)


def test_watched_path_observations_are_stored(tmp_path) -> None:
    watched = tmp_path / "watched.txt"
    watched.write_text("abc")
    result = _run_with_output_dir(
        tmp_path,
        [sys.executable, "-c", "pass"],
        watch_paths=[str(watched)],
    )
    sample = _events(result.telemetry_path, "sample")[-1]
    watched_event = sample["watched_paths"][0]
    assert watched_event["original_path"] == str(watched)
    assert watched_event["kind"] == "file"
    assert watched_event["size_bytes"] == 3
    assert watched_event["disk_usage"]["free_bytes"] is not None
    summary = _read_summary(result.summary_path)
    assert summary["final_watched_paths"][0]["size_bytes"] == 3


def test_no_watched_paths_still_writes_empty_watch_facts(tmp_path) -> None:
    result = _run_with_output_dir(tmp_path, [sys.executable, "-c", "pass"])
    assert _events(result.telemetry_path, "sample")[-1]["watched_paths"] == []
    assert _read_summary(result.summary_path)["final_watched_paths"] == []


def test_nonzero_child_exit_writes_telemetry_and_summary(tmp_path) -> None:
    result = _run_with_output_dir(tmp_path, [sys.executable, "-c", "raise SystemExit(7)"])
    assert result.exit_code == 7
    assert _event(result.telemetry_path, "run_finished")["exit_code"] == 7
    assert _read_summary(result.summary_path)["exit_code"] == 7


def test_sigint_run_writes_final_telemetry_and_summary(tmp_path) -> None:
    output_dir = tmp_path / "rs-out"
    ready_path = tmp_path / "ready.txt"
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
            "--output-dir",
            str(output_dir),
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
        process.communicate(timeout=8)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    assert process.returncode == EXIT_SIGINT
    summaries = list((output_dir / "runs").glob("*/summary.json"))
    telemetry_files = list((output_dir / "runs").glob("*/telemetry.jsonl"))
    assert len(summaries) == 1
    assert len(telemetry_files) == 1
    assert _read_summary(str(summaries[0]))["exit_code"] == EXIT_SIGINT
    assert _event(str(telemetry_files[0]), "run_finished")["exit_code"] == EXIT_SIGINT


def test_command_not_found_remains_deterministic(tmp_path) -> None:
    output_dir = tmp_path / "rs-out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--output-dir",
            str(output_dir),
            "--",
            "runsentry-definitely-not-real-007",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == EXIT_COMMAND_NOT_FOUND
    assert "command not found" in result.stderr


def test_output_directory_creation_failure_does_not_run_child(tmp_path) -> None:
    output_dir_as_file = tmp_path / "not-a-dir"
    output_dir_as_file.write_text("x")
    marker = tmp_path / "marker.txt"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--output-dir",
            str(output_dir_as_file),
            "--",
            sys.executable,
            "-c",
            f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == EXIT_INTERNAL_ERROR
    assert "could not initialize telemetry output" in result.stderr
    assert not marker.exists()


def test_telemetry_write_failure_during_run_does_not_kill_child(monkeypatch, tmp_path) -> None:
    original_write_event = TelemetryWriter.write_event

    def fail_after_started(self, event, flush=False):
        if event["event_type"] == "sample":
            self._record_telemetry_error(OSError("simulated write failure"))
            return
        original_write_event(self, event, flush)

    monkeypatch.setattr(TelemetryWriter, "write_event", fail_after_started)
    marker = tmp_path / "completed.txt"
    result = execute_command(
        RunSpec(
            name="write-failure",
            argv=[
                sys.executable,
                "-c",
                f"import pathlib; pathlib.Path({str(marker)!r}).write_text('done')",
            ],
            output_dir=str(tmp_path / "rs-out"),
        )
    )
    assert result.exit_code == 0
    assert marker.read_text() == "done"


def test_summary_write_failure_does_not_alter_child_exit(monkeypatch, tmp_path) -> None:
    original_write_summary = TelemetryWriter.write_summary

    def simulated_summary_failure(self, **kwargs):
        self.summary_failed = True
        self.summary_error = "simulated summary failure"
        return None

    monkeypatch.setattr(TelemetryWriter, "write_summary", simulated_summary_failure)
    result = _run_with_output_dir(tmp_path, [sys.executable, "-c", "raise SystemExit(7)"])
    monkeypatch.setattr(TelemetryWriter, "write_summary", original_write_summary)
    assert result.exit_code == 7
    assert not Path(result.summary_path).exists()
    assert _event(result.telemetry_path, "run_finished")["exit_code"] == 7


def test_high_volume_stdout_stderr_regression_with_telemetry(tmp_path) -> None:
    output_dir = tmp_path / "rs-out"
    payload_size = 65536 * 4
    script = (
        "import os, sys, threading\n"
        f"payload_size = {payload_size}\n"
        "def write_all(fd, byte):\n"
        "    chunk = byte * 8192\n"
        "    remaining = payload_size\n"
        "    while remaining:\n"
        "        n = min(len(chunk), remaining)\n"
        "        os.write(fd, chunk[:n])\n"
        "        remaining -= n\n"
        "threads = [threading.Thread(target=write_all, args=(sys.stdout.fileno(), b'o')), threading.Thread(target=write_all, args=(sys.stderr.fileno(), b'e'))]\n"
        "[t.start() for t in threads]\n"
        "[t.join() for t in threads]\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--output-dir",
            str(output_dir),
            "--",
            sys.executable,
            "-c",
            script,
        ],
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == b"o" * payload_size
    assert result.stderr == b"e" * payload_size
    summary = _read_summary(str(next((output_dir / "runs").glob("*/summary.json"))))
    assert summary["stdout"]["total_bytes"] == payload_size
    assert summary["stderr"]["total_bytes"] == payload_size


def test_no_unbounded_event_list_is_retained(tmp_path) -> None:
    writer = TelemetryWriter.create(str(tmp_path / "rs-out"))
    try:
        assert not hasattr(writer, "events")
        assert not hasattr(writer, "samples")
        assert not hasattr(writer, "history")
    finally:
        writer.close()


def test_run_id_uniqueness_for_quick_runs() -> None:
    run_ids = {generate_run_id() for _ in range(100)}
    assert len(run_ids) == 100


def test_watch_after_boundary_is_not_runsentry_watch_config(tmp_path) -> None:
    output_dir = tmp_path / "rs-out"
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
            "--output-dir",
            str(output_dir),
            "--",
            sys.executable,
            "-c",
            script,
            str(argv_path),
            "--watch",
            "child",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(argv_path.read_text()) == ["--watch", "child"]
    summary = _read_summary(str(next((output_dir / "runs").glob("*/summary.json"))))
    assert summary["final_watched_paths"] == []


def test_runsentry_output_is_gitignored() -> None:
    ignore_text = Path(".gitignore").read_text()
    assert ".runsentry/" in ignore_text


def _run_with_output_dir(
    tmp_path: Path,
    argv: list[str],
    name: str | None = "telemetry",
    watch_paths: list[str] | None = None,
):
    return execute_command(
        RunSpec(
            name=name,
            argv=argv,
            sample_interval_s=1.0,
            watch_paths=watch_paths,
            output_dir=str(tmp_path / "rs-out"),
        )
    )


def _read_events(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def _events(path: str, event_type: str) -> list[dict]:
    return [event for event in _read_events(path) if event["event_type"] == event_type]


def _event(path: str, event_type: str) -> dict:
    matching = _events(path, event_type)
    assert matching
    return matching[-1]


def _read_summary(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _wait_for_path(path: Path, timeout_s: float = 5.0) -> None:
    deadline_s = time.monotonic() + timeout_s
    while time.monotonic() < deadline_s:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")
