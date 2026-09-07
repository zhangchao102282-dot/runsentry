import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from helpers import _resource, _stream, _watch
from runsentry.execution import EXIT_SIGINT, RunSpec, execute_command
from runsentry.health import HealthConfig, HealthState, HealthStateMachine


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


def _read_events(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def _wait_for_path(path: Path, timeout_s: float = 5.0) -> None:
    deadline_s = time.monotonic() + timeout_s
    while time.monotonic() < deadline_s:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")
