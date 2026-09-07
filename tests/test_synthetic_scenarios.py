import json
import subprocess
import sys
from pathlib import Path

from runsentry.health import HealthConfig, HealthState, HealthStateMachine
from tests.test_health import _resource, _stream, _watch


SYNTHETIC_DIR = Path(__file__).parent / "synthetic"


def test_healthy_cpu_scenario(tmp_path) -> None:
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "healthy_cpu.py",
        "--duration-seconds",
        "0.4",
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    assert "SUSPECTED_STALL" not in _health_states(telemetry, summary)
    assert summary["stdout"]["total_bytes"] > 0


def test_healthy_io_scenario_records_output_and_watch_growth(tmp_path) -> None:
    watched = tmp_path / "healthy-io.log"
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "healthy_io.py",
        "--output-file",
        str(watched),
        "--iterations",
        "4",
        "--delay-seconds",
        "0.05",
        watch_paths=[watched],
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    assert "SUSPECTED_STALL" not in _health_states(telemetry, summary)
    assert summary["stdout"]["total_bytes"] > 0
    watched_summary = summary["final_watched_paths"][0]
    assert watched_summary["kind"] == "file"
    assert watched_summary["size_bytes"] > 0
    assert watched_summary["disk_usage"]["free_bytes"] is not None


def test_quiet_but_healthy_scenario_does_not_stall_on_silence(tmp_path) -> None:
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "quiet_but_healthy.py",
        "--duration-seconds",
        "0.4",
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    states = _health_states(telemetry, summary)
    assert "SUSPECTED_STALL" not in states
    assert summary["stdout"]["total_bytes"] == 0
    assert summary["stderr"]["total_bytes"] == 0


def test_memory_growth_scenario_records_rss_without_oom_claims(tmp_path) -> None:
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "memory_growth.py",
        "--chunks",
        "4",
        "--chunk-kib",
        "64",
        "--delay-seconds",
        "0.05",
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    assert "peak_root_rss_bytes" in summary
    assert summary["peak_root_rss_bytes"] is None or summary["peak_root_rss_bytes"] >= 0
    _assert_no_prediction_or_intervention_fields(telemetry, summary)


def test_hang_after_60s_scenario_is_bounded_and_not_immediately_stalled(tmp_path) -> None:
    watched = tmp_path / "hang-watch.txt"
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "hang_after_60s.py",
        "--after-seconds",
        "0.1",
        "--hang-seconds",
        "0.3",
        "--watch-file",
        str(watched),
        watch_paths=[watched],
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    assert "SUSPECTED_STALL" not in _health_states(telemetry, summary)
    assert summary["final_watched_paths"][0]["size_bytes"] > 0


def test_hang_after_60s_health_machine_can_reach_stall_only_after_window() -> None:
    config = HealthConfig(
        starting_window_s=0.5,
        quiet_window_s=0.5,
        suspected_stall_window_s=1.0,
        minimal_cpu_activity_threshold=1.0,
    )
    machine = HealthStateMachine(config)
    first = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=0.1, cpu_percent=0.0),
        stdout_activity=_stream("stdout", total_bytes=10),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    quiet = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=0.6, cpu_percent=0.0),
        stdout_activity=_stream("stdout", total_bytes=10),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    stalled = machine.assess_sample(
        resource_snapshot=_resource(elapsed_s=1.2, cpu_percent=0.0),
        stdout_activity=_stream("stdout", total_bytes=10),
        stderr_activity=_stream("stderr"),
        watched_paths=(_watch("out", size=10, mtime=1.0),),
    )
    assert first.state == HealthState.STARTING
    assert quiet.state == HealthState.QUIET
    assert stalled.state == HealthState.SUSPECTED_STALL


def test_crash_after_60s_scenario_fails_and_drains_tail_output(tmp_path) -> None:
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "crash_after_60s.py",
        "--after-seconds",
        "0.1",
        "--exit-code",
        "7",
    )
    assert result.returncode == 7
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "FAILED", 7)
    assert summary["stderr"]["total_bytes"] > 0


def test_child_process_crash_does_not_make_successful_root_failed(tmp_path) -> None:
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "child_process_crash.py",
        "--root-exit-code",
        "0",
        "--child-exit-code",
        "7",
        "--linger-seconds",
        "0.2",
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    assert summary["child_returncode"] == 0
    assert "root_exit_nonzero" not in summary["final_reason_codes"]


def test_disk_writer_scenario_records_directory_growth_and_no_disk_prediction(tmp_path) -> None:
    watched_dir = tmp_path / "disk-output"
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "disk_writer.py",
        "--output-dir",
        str(watched_dir),
        "--files",
        "3",
        "--bytes-per-file",
        "64",
        "--delay-seconds",
        "0.05",
        watch_paths=[watched_dir],
    )
    assert result.returncode == 0
    _assert_common_telemetry(telemetry, summary)
    _assert_final(summary, "COMPLETE", 0)
    watched_summary = summary["final_watched_paths"][0]
    assert watched_summary["kind"] == "directory"
    assert watched_summary["aggregate_size_bytes"] == 192
    assert watched_summary["file_count"] == 3
    assert watched_summary["disk_usage"]["free_bytes"] is not None
    _assert_no_prediction_or_intervention_fields(telemetry, summary)


def test_synthetic_stdout_content_is_not_persisted(tmp_path) -> None:
    result, telemetry, summary = _run_scenario(
        tmp_path,
        "healthy_cpu.py",
        "--duration-seconds",
        "0.1",
    )
    assert result.returncode == 0
    serialized_telemetry = "\n".join(json.dumps(event, sort_keys=True) for event in telemetry)
    serialized_summary = json.dumps(summary, sort_keys=True)
    assert "healthy_cpu: start" not in serialized_telemetry
    assert "healthy_cpu: done" not in serialized_telemetry
    assert "healthy_cpu: start" not in serialized_summary
    assert "healthy_cpu: done" not in serialized_summary


def _run_scenario(
    tmp_path: Path,
    script_name: str,
    *script_args: str,
    watch_paths: list[Path] | None = None,
):
    output_dir = tmp_path / "runsentry-output"
    command = [
        sys.executable,
        "-m",
        "runsentry",
        "run",
        "--output-dir",
        str(output_dir),
    ]
    for watch_path in watch_paths or []:
        command.extend(["--watch", str(watch_path)])
    command.extend(["--", sys.executable, str(SYNTHETIC_DIR / script_name), *script_args])
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    run_dir = _single_run_dir(output_dir)
    telemetry = _read_telemetry(run_dir / "telemetry.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text())
    return result, telemetry, summary


def _single_run_dir(output_dir: Path) -> Path:
    run_dirs = list((output_dir / "runs").glob("*"))
    assert len(run_dirs) == 1
    return run_dirs[0]


def _read_telemetry(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _assert_common_telemetry(telemetry: list[dict], summary: dict) -> None:
    assert [event["event_type"] for event in telemetry if event["event_type"] == "run_started"]
    assert [event["event_type"] for event in telemetry if event["event_type"] == "sample"]
    assert [event["event_type"] for event in telemetry if event["event_type"] == "run_finished"]
    for event in telemetry:
        assert event["schema_version"] == "rs-p0-telemetry-v1"
        assert event["run_id"] == summary["run_id"]
        assert "timestamp_epoch_s" in event
        assert "elapsed_s" in event
    assert "final_health_state" in summary
    assert "health_transition_history" in summary
    _assert_no_prediction_or_intervention_fields(telemetry, summary)


def _assert_final(summary: dict, final_health_state: str, exit_code: int) -> None:
    assert summary["final_health_state"] == final_health_state
    assert summary["exit_code"] == exit_code
    assert summary["health_terminal"] is True


def _health_states(telemetry: list[dict], summary: dict) -> set[str]:
    states = {
        event["health_state"]
        for event in telemetry
        if event["event_type"] in {"sample", "run_finished"}
    }
    states.add(summary["final_health_state"])
    return states


def _assert_no_prediction_or_intervention_fields(
    telemetry: list[dict],
    summary: dict,
) -> None:
    forbidden = {
        "oom_risk",
        "disk_exhaustion_eta",
        "job_eta",
        "notification_status",
        "auto_kill_action",
    }
    for event in telemetry:
        assert forbidden.isdisjoint(event.keys())
    assert forbidden.isdisjoint(summary.keys())
