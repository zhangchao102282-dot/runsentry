import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from runsentry.execution import EXIT_SIGINT, RunSpec, execute_command
from runsentry.health import HealthConfig, HealthState, HealthStateMachine
from runsentry.observation import (
    ProcessIdentity,
    ProcessObservation,
    ResourceSnapshot,
    SwapSnapshot,
    SystemMemorySnapshot,
)
from runsentry.output import StreamActivitySnapshot
from runsentry.watch import DiskUsageSnapshot, WatchedPathObservation


TEST_HEALTH_CONFIG = HealthConfig(
    starting_window_s=1.0,
    quiet_window_s=2.0,
    suspected_stall_window_s=3.0,
    minimal_cpu_activity_threshold=1.0,
)


def test_initial_state_is_starting_during_window() -> None:
    machine = HealthStateMachine(TEST_HEALTH_CONFIG)
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=0.5, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.STARTING
    assert "starting_window" in assessment.reason_codes


def test_stdout_activity_leads_to_healthy() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.5, cpu_percent=0.0),
        stdout_activity=_stream("stdout", total_bytes=10),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.HEALTHY
    assert "recent_output_activity" in assessment.reason_codes


def test_stderr_activity_leads_to_healthy() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.5, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr", total_bytes=5),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.HEALTHY
    assert "recent_output_activity" in assessment.reason_codes


def test_watched_file_growth_leads_to_healthy() -> None:
    machine = _primed_machine()
    machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.1, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.5, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=15, mtime=2.0, size_delta=5),),
    )
    assert assessment.state == HealthState.HEALTHY
    assert "recent_watch_growth" in assessment.reason_codes


def test_cpu_bound_silent_task_leads_to_healthy() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.5, cpu_percent=25.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(),
    )
    assert assessment.state == HealthState.HEALTHY
    assert "recent_cpu_activity" in assessment.reason_codes


def test_quiet_sleeping_task_becomes_quiet_before_stall_window() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=2.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.QUIET
    assert "insufficient_evidence_quiet" in assessment.reason_codes


def test_quiet_but_healthy_style_silence_alone_never_causes_suspected_stall() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=10.0, cpu_percent=None),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(),
    )
    assert assessment.state == HealthState.QUIET
    assert "cpu_unavailable" in assessment.reason_codes


def test_no_watch_path_does_not_count_as_stall_evidence() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=10.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(),
    )
    assert assessment.state == HealthState.QUIET


def test_output_observation_unavailable_does_not_count_as_silence() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=10.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout", read_error="read failed"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.QUIET
    assert "output_observation_unavailable" in assessment.reason_codes


def test_watched_path_unavailable_does_not_count_as_no_growth() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=10.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", kind="inaccessible", unavailable="permission_denied"),),
    )
    assert assessment.state == HealthState.QUIET
    assert "watched_path_unavailable" in assessment.reason_codes


def test_cpu_unavailable_does_not_count_as_low_cpu_by_itself() -> None:
    machine = _primed_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=10.0, cpu_percent=None),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.QUIET
    assert "cpu_unavailable" in assessment.reason_codes


def test_sustained_multi_signal_inactivity_can_become_suspected_stall() -> None:
    machine = _primed_machine()
    machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.1, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=4.5, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.SUSPECTED_STALL
    assert "sustained_multi_signal_inactivity" in assessment.reason_codes


def test_suspected_stall_recovers_to_healthy_on_output_activity() -> None:
    machine = _suspected_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=5.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout", total_bytes=1),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.HEALTHY
    assert "recent_output_activity" in assessment.reason_codes


def test_suspected_stall_recovers_to_healthy_on_watch_growth() -> None:
    machine = _suspected_machine()
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=5.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=20, mtime=2.0, size_delta=10),),
    )
    assert assessment.state == HealthState.HEALTHY
    assert "recent_watch_growth" in assessment.reason_codes


def test_exit_zero_produces_complete() -> None:
    machine = _primed_machine()
    assessment = machine.assess_finished(exit_code=0, elapsed_s=2.0)
    assert assessment.state == HealthState.COMPLETE
    assert assessment.terminal
    assert assessment.reason_codes == ("root_exit_zero",)


def test_exit_zero_with_known_live_descendants_does_not_produce_complete() -> None:
    machine = _primed_machine()
    assessment = machine.assess_finished(
        exit_code=0,
        elapsed_s=2.0,
        alive_known_process_count=1,
    )
    assert assessment.state == HealthState.QUIET
    assert assessment.terminal
    assert assessment.reason_codes == ("root_exit_zero_known_descendants_alive",)


def test_nonzero_exit_produces_failed() -> None:
    machine = _primed_machine()
    assessment = machine.assess_finished(exit_code=7, elapsed_s=2.0)
    assert assessment.state == HealthState.FAILED
    assert assessment.terminal
    assert assessment.reason_codes == ("root_exit_nonzero",)


def test_sigint_is_interrupted_terminal_semantics_not_complete() -> None:
    machine = _primed_machine()
    assessment = machine.assess_finished(exit_code=130, elapsed_s=2.0)
    assert assessment.state == HealthState.QUIET
    assert assessment.terminal
    assert assessment.reason_codes == ("interrupted_sigint",)


def test_telemetry_sample_events_include_health_state_and_reason_codes(tmp_path) -> None:
    result = execute_command(
        RunSpec(
            name="health-telemetry",
            argv=[sys.executable, "-c", "pass"],
            output_dir=str(tmp_path / "rs-out"),
        )
    )
    events = _read_events(result.telemetry_path)
    sample = [event for event in events if event["event_type"] == "sample"][-1]
    assert sample["health_state"] in {state.value for state in HealthState}
    assert isinstance(sample["reason_codes"], list)


def test_summary_includes_final_health_and_transition_history(tmp_path) -> None:
    result = execute_command(
        RunSpec(
            name="health-summary",
            argv=[sys.executable, "-c", "pass"],
            output_dir=str(tmp_path / "rs-out"),
        )
    )
    summary = json.loads(Path(result.summary_path).read_text())
    assert summary["final_health_state"] == HealthState.COMPLETE.value
    assert summary["health_terminal"] is True
    assert summary["final_reason_codes"] == ["root_exit_zero"]
    assert summary["health_transition_history"]


def test_high_volume_stdout_stderr_still_passes_with_health(tmp_path) -> None:
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
            str(tmp_path / "rs-out"),
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


def test_sigint_regression_with_health_summary(tmp_path) -> None:
    ready_path = tmp_path / "ready.txt"
    output_dir = tmp_path / "rs-out"
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
    summary_path = next((output_dir / "runs").glob("*/summary.json"))
    summary = json.loads(summary_path.read_text())
    assert summary["final_health_state"] == HealthState.QUIET.value
    assert summary["final_reason_codes"] == ["interrupted_sigint"]
    assert summary["health_terminal"] is True


def _primed_machine() -> HealthStateMachine:
    machine = HealthStateMachine(TEST_HEALTH_CONFIG)
    machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=0.0, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(),
    )
    return machine


def _suspected_machine() -> HealthStateMachine:
    machine = _primed_machine()
    machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.1, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assessment = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=4.5, cpu_percent=0.0),
        stdout_activity=_stream("stdout"),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert assessment.state == HealthState.SUSPECTED_STALL
    return machine


def _resource(
    *,
    elapsed_s: float,
    cpu_percent: float | None,
    observation_complete: bool = True,
) -> ResourceSnapshot:
    identity = ProcessIdentity(pid=123, create_time_epoch_s=100.0)
    root_observation = ProcessObservation(
        identity=identity,
        role="root",
        alive=True,
        status="running",
        cpu_percent=cpu_percent,
        rss_bytes=1024,
    )
    return ResourceSnapshot(
        observed_monotonic_s=elapsed_s,
        elapsed_s=elapsed_s,
        root_identity=identity,
        root_observation=root_observation,
        current_observable_process_count=1,
        current_alive_known_process_count=1,
        observable_descendant_count=0,
        tree_cpu_percent=cpu_percent,
        tree_rss_bytes=1024,
        tree_rss_partial=False,
        current_observable_members=(identity,),
        known_descendants=(),
        disappeared_descendants=(),
        inaccessible_process_count=0,
        pid_reuse_observed=False,
        observation_complete=observation_complete,
        unavailable_reasons=(),
        system_memory=SystemMemorySnapshot(
            total_bytes=100,
            available_bytes=50,
            used_bytes=50,
            percent=50.0,
        ),
        swap=SwapSnapshot(
            total_bytes=0,
            used_bytes=0,
            free_bytes=0,
            percent=0.0,
        ),
    )


def _stream(
    name: str,
    *,
    total_bytes: int = 0,
    read_error: str | None = None,
) -> StreamActivitySnapshot:
    return StreamActivitySnapshot(
        name=name,
        total_bytes=total_bytes,
        total_chunks=1 if total_bytes else 0,
        first_activity_monotonic_s=1.0 if total_bytes else None,
        last_activity_monotonic_s=1.0 if total_bytes else None,
        read_error=read_error,
        display_error=None,
        eof=False,
    )


def _watch(
    original_path: str,
    *,
    size: int | None = None,
    mtime: float | None = None,
    size_delta: int | None = None,
    kind: str = "file",
    unavailable: str | None = None,
) -> WatchedPathObservation:
    exists = kind not in {"missing", "inaccessible"}
    return WatchedPathObservation(
        original_path=original_path,
        absolute_path=f"/tmp/{original_path}",
        exists=exists,
        kind=kind,
        size_bytes=size if kind == "file" else None,
        aggregate_size_bytes=size if kind == "directory" else None,
        file_count=1 if kind == "directory" and size is not None else None,
        latest_mtime_epoch_s=mtime,
        device_id=1 if exists else None,
        inode=1 if exists else None,
        changed_since_previous_sample=size_delta not in (None, 0),
        size_delta_bytes=size_delta,
        mtime_changed_since_previous_sample=None,
        replaced_since_previous_sample=None,
        observation_partial=unavailable is not None,
        unavailable_reason=unavailable,
        disk_usage=DiskUsageSnapshot(
            filesystem_path="/tmp",
            total_bytes=1000,
            used_bytes=100,
            free_bytes=900,
        ),
    )


def _read_events(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def _wait_for_path(path: Path, timeout_s: float = 5.0) -> None:
    deadline_s = time.monotonic() + timeout_s
    while time.monotonic() < deadline_s:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")
