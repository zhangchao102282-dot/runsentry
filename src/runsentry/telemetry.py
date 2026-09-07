from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .health import (
    HealthAssessment,
    HealthTransition,
    serialize_assessment,
    serialize_transition_history,
)
from .observation import ProcessIdentity, ProcessObservation, ResourceSnapshot
from .output import StreamActivitySnapshot
from .watch import DiskUsageSnapshot, WatchedPathObservation

SCHEMA_VERSION = "rs-p0-telemetry-v1"
DEFAULT_OUTPUT_ROOT = ".runsentry"


class TelemetryInitializationError(Exception):
    pass


@dataclass(frozen=True)
class TelemetryPaths:
    run_dir: Path
    telemetry_path: Path
    summary_path: Path


@dataclass
class TelemetryWriter:
    run_id: str
    paths: TelemetryPaths
    start_timestamp_epoch_s: float
    cwd: str
    telemetry_failed: bool = False
    telemetry_error: str | None = None
    summary_failed: bool = False
    summary_error: str | None = None
    sample_count: int = 0
    peak_root_rss_bytes: int | None = None
    peak_tree_rss_bytes: int | None = None
    max_observable_process_count: int = 0
    max_observable_descendant_count: int = 0
    _file: Any = None

    @classmethod
    def create(cls, output_dir: str | None = None) -> "TelemetryWriter":
        cwd = os.getcwd()
        run_id = generate_run_id()
        output_root = Path(output_dir) if output_dir is not None else Path(DEFAULT_OUTPUT_ROOT)
        run_dir = output_root / "runs" / run_id
        telemetry_path = run_dir / "telemetry.jsonl"
        summary_path = run_dir / "summary.json"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            telemetry_file = telemetry_path.open("w", encoding="utf-8")
        except OSError as exc:
            raise TelemetryInitializationError(
                f"could not initialize telemetry output: {exc}"
            ) from exc
        return cls(
            run_id=run_id,
            paths=TelemetryPaths(run_dir, telemetry_path, summary_path),
            start_timestamp_epoch_s=_now_epoch_s(),
            cwd=cwd,
            _file=telemetry_file,
        )

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError as exc:
                self._record_telemetry_error(exc)
            finally:
                self._file = None

    def write_run_started(
        self,
        *,
        name: str | None,
        argv: list[str],
        root_pid: int,
        root_create_time_epoch_s: float | None,
        watched_paths: list[str],
        sample_interval_s: float,
    ) -> None:
        self.write_event(
            {
                **self._base_event("run_started"),
                "name": name,
                "argv": list(argv),
                "root_pid": root_pid,
                "root_create_time_epoch_s": root_create_time_epoch_s,
                "start_timestamp_epoch_s": self.start_timestamp_epoch_s,
                "cwd": self.cwd,
                "watched_paths": list(watched_paths),
                "sample_interval_s": sample_interval_s,
            },
            flush=True,
        )

    def write_sample(
        self,
        *,
        resource_snapshot: ResourceSnapshot | None,
        stdout_activity: StreamActivitySnapshot,
        stderr_activity: StreamActivitySnapshot,
        watched_paths: tuple[WatchedPathObservation, ...],
        health_assessment: HealthAssessment,
    ) -> None:
        self.sample_count += 1
        self._update_peaks(resource_snapshot)
        self.write_event(
            {
                **self._base_event("sample"),
                "process": serialize_resource_snapshot(resource_snapshot),
                "stdout": serialize_stream_activity(stdout_activity),
                "stderr": serialize_stream_activity(stderr_activity),
                "watched_paths": serialize_watched_paths(watched_paths),
                "health_state": health_assessment.state.value,
                "reason_codes": list(health_assessment.reason_codes),
            }
        )

    def write_run_finished(
        self,
        *,
        name: str | None,
        argv: list[str],
        exit_code: int,
        child_returncode: int | None,
        output_drained: bool,
        resource_snapshot: ResourceSnapshot | None,
        stdout_activity: StreamActivitySnapshot,
        stderr_activity: StreamActivitySnapshot,
        watched_paths: tuple[WatchedPathObservation, ...],
        health_assessment: HealthAssessment,
        health_transitions: tuple[HealthTransition, ...],
    ) -> None:
        self._update_peaks(resource_snapshot)
        end_timestamp_epoch_s = _now_epoch_s()
        duration_s = max(0.0, end_timestamp_epoch_s - self.start_timestamp_epoch_s)
        finished = {
            **self._base_event("run_finished", timestamp_epoch_s=end_timestamp_epoch_s),
            "end_timestamp_epoch_s": end_timestamp_epoch_s,
            "duration_s": duration_s,
            "exit_code": exit_code,
            "child_returncode": child_returncode,
            "output_drained": output_drained,
            "stdout": serialize_stream_activity(stdout_activity),
            "stderr": serialize_stream_activity(stderr_activity),
            "process": serialize_resource_snapshot(resource_snapshot),
            "watched_paths": serialize_watched_paths(watched_paths),
            "peaks": self._peaks_dict(),
            "health_state": health_assessment.state.value,
            "reason_codes": list(health_assessment.reason_codes),
            "health": serialize_assessment(health_assessment),
            "health_transition_history": serialize_transition_history(
                health_transitions
            ),
        }
        self.write_event(finished, flush=True)
        self.write_summary(
            name=name,
            argv=argv,
            end_timestamp_epoch_s=end_timestamp_epoch_s,
            duration_s=duration_s,
            exit_code=exit_code,
            child_returncode=child_returncode,
            output_drained=output_drained,
            stdout_activity=stdout_activity,
            stderr_activity=stderr_activity,
            watched_paths=watched_paths,
            health_assessment=health_assessment,
            health_transitions=health_transitions,
        )

    def write_summary(
        self,
        *,
        name: str | None,
        argv: list[str],
        end_timestamp_epoch_s: float,
        duration_s: float,
        exit_code: int,
        child_returncode: int | None,
        output_drained: bool,
        stdout_activity: StreamActivitySnapshot,
        stderr_activity: StreamActivitySnapshot,
        watched_paths: tuple[WatchedPathObservation, ...],
        health_assessment: HealthAssessment,
        health_transitions: tuple[HealthTransition, ...],
    ) -> None:
        summary = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "name": name,
            "argv": list(argv),
            "cwd": self.cwd,
            "start_timestamp_epoch_s": self.start_timestamp_epoch_s,
            "end_timestamp_epoch_s": end_timestamp_epoch_s,
            "duration_s": duration_s,
            "exit_code": exit_code,
            "child_returncode": child_returncode,
            "sample_count": self.sample_count,
            "output_drained": output_drained,
            "stdout": serialize_stream_activity(stdout_activity),
            "stderr": serialize_stream_activity(stderr_activity),
            **self._peaks_dict(),
            "final_watched_paths": serialize_watched_paths(watched_paths),
            "final_health_state": health_assessment.state.value,
            "final_reason_codes": list(health_assessment.reason_codes),
            "health_terminal": health_assessment.terminal,
            "health_transition_history": serialize_transition_history(
                health_transitions
            ),
            "telemetry_file_path": str(self.paths.telemetry_path),
            "consciously_absent_fields": [
                "stall_status",
                "oom_risk",
                "disk_exhaustion_eta",
                "job_eta",
            ],
        }
        try:
            with self.paths.summary_path.open("w", encoding="utf-8") as summary_file:
                json.dump(summary, summary_file, sort_keys=True)
                summary_file.write("\n")
                summary_file.flush()
        except OSError as exc:
            self.summary_failed = True
            self.summary_error = f"{type(exc).__name__}: {exc}"
            _safe_diagnostic(f"runsentry: summary write failed: {self.summary_error}")

    def write_event(self, event: dict[str, Any], flush: bool = False) -> None:
        if self.telemetry_failed or self._file is None:
            return
        try:
            self._file.write(json.dumps(event, sort_keys=True) + "\n")
            if flush:
                self._file.flush()
        except (OSError, TypeError, ValueError) as exc:
            self._record_telemetry_error(exc)

    def _base_event(
        self,
        event_type: str,
        timestamp_epoch_s: float | None = None,
    ) -> dict[str, Any]:
        timestamp = timestamp_epoch_s if timestamp_epoch_s is not None else _now_epoch_s()
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "event_type": event_type,
            "timestamp_epoch_s": timestamp,
            "elapsed_s": max(0.0, timestamp - self.start_timestamp_epoch_s),
        }

    def _update_peaks(self, snapshot: ResourceSnapshot | None) -> None:
        if snapshot is None:
            return
        root_rss = snapshot.root_observation.rss_bytes
        if root_rss is not None:
            self.peak_root_rss_bytes = _max_optional(self.peak_root_rss_bytes, root_rss)
        if snapshot.tree_rss_bytes is not None:
            self.peak_tree_rss_bytes = _max_optional(
                self.peak_tree_rss_bytes,
                snapshot.tree_rss_bytes,
            )
        self.max_observable_process_count = max(
            self.max_observable_process_count,
            snapshot.current_observable_process_count,
        )
        self.max_observable_descendant_count = max(
            self.max_observable_descendant_count,
            snapshot.observable_descendant_count,
        )

    def _peaks_dict(self) -> dict[str, int | None]:
        return {
            "peak_root_rss_bytes": self.peak_root_rss_bytes,
            "peak_tree_rss_bytes": self.peak_tree_rss_bytes,
            "max_observable_process_count": self.max_observable_process_count,
            "max_observable_descendant_count": self.max_observable_descendant_count,
        }

    def _record_telemetry_error(self, exc: BaseException) -> None:
        self.telemetry_failed = True
        self.telemetry_error = f"{type(exc).__name__}: {exc}"
        _safe_diagnostic(f"runsentry: telemetry write failed: {self.telemetry_error}")


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:12]}"


def serialize_resource_snapshot(snapshot: ResourceSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "observed_monotonic_s": snapshot.observed_monotonic_s,
        "elapsed_s": snapshot.elapsed_s,
        "root_identity": serialize_process_identity(snapshot.root_identity),
        "root_observation": serialize_process_observation(snapshot.root_observation),
        "current_observable_process_count": snapshot.current_observable_process_count,
        "current_alive_known_process_count": snapshot.current_alive_known_process_count,
        "observable_descendant_count": snapshot.observable_descendant_count,
        "tree_cpu_percent": snapshot.tree_cpu_percent,
        "tree_rss_bytes": snapshot.tree_rss_bytes,
        "tree_rss_partial": snapshot.tree_rss_partial,
        "current_observable_members": [
            serialize_process_identity(identity)
            for identity in snapshot.current_observable_members
        ],
        "known_descendants": [
            serialize_process_identity(identity) for identity in snapshot.known_descendants
        ],
        "disappeared_descendants": [
            serialize_process_identity(identity)
            for identity in snapshot.disappeared_descendants
        ],
        "inaccessible_process_count": snapshot.inaccessible_process_count,
        "pid_reuse_observed": snapshot.pid_reuse_observed,
        "observation_complete": snapshot.observation_complete,
        "unavailable_reasons": list(snapshot.unavailable_reasons),
        "system_memory": {
            "total_bytes": snapshot.system_memory.total_bytes,
            "available_bytes": snapshot.system_memory.available_bytes,
            "used_bytes": snapshot.system_memory.used_bytes,
            "percent": snapshot.system_memory.percent,
            "unavailable": snapshot.system_memory.unavailable,
        },
        "swap": {
            "total_bytes": snapshot.swap.total_bytes,
            "used_bytes": snapshot.swap.used_bytes,
            "free_bytes": snapshot.swap.free_bytes,
            "percent": snapshot.swap.percent,
            "unavailable": snapshot.swap.unavailable,
        },
    }


def serialize_process_identity(identity: ProcessIdentity) -> dict[str, Any]:
    return {
        "pid": identity.pid,
        "create_time_epoch_s": identity.create_time_epoch_s,
    }


def serialize_process_observation(observation: ProcessObservation) -> dict[str, Any]:
    return {
        "identity": serialize_process_identity(observation.identity),
        "role": observation.role,
        "alive": observation.alive,
        "status": observation.status,
        "cpu_percent": observation.cpu_percent,
        "rss_bytes": observation.rss_bytes,
        "access_denied": observation.access_denied,
        "zombie": observation.zombie,
        "disappeared": observation.disappeared,
        "pid_reused": observation.pid_reused,
    }


def serialize_stream_activity(activity: StreamActivitySnapshot) -> dict[str, Any]:
    return {
        "name": activity.name,
        "total_bytes": activity.total_bytes,
        "total_chunks": activity.total_chunks,
        "first_activity_monotonic_s": activity.first_activity_monotonic_s,
        "last_activity_monotonic_s": activity.last_activity_monotonic_s,
        "eof": activity.eof,
        "read_error": activity.read_error is not None,
        "display_error": activity.display_error is not None,
    }


def serialize_watched_paths(
    observations: tuple[WatchedPathObservation, ...],
) -> list[dict[str, Any]]:
    return [serialize_watched_path(observation) for observation in observations]


def serialize_watched_path(observation: WatchedPathObservation) -> dict[str, Any]:
    return {
        "original_path": observation.original_path,
        "absolute_path": observation.absolute_path,
        "exists": observation.exists,
        "kind": observation.kind,
        "size_bytes": observation.size_bytes,
        "aggregate_size_bytes": observation.aggregate_size_bytes,
        "file_count": observation.file_count,
        "latest_mtime_epoch_s": observation.latest_mtime_epoch_s,
        "identity": {
            "device_id": observation.device_id,
            "inode": observation.inode,
        },
        "changed_since_previous_sample": observation.changed_since_previous_sample,
        "size_delta_bytes": observation.size_delta_bytes,
        "mtime_changed_since_previous_sample": (
            observation.mtime_changed_since_previous_sample
        ),
        "replaced_since_previous_sample": observation.replaced_since_previous_sample,
        "observation_partial": observation.observation_partial,
        "unavailable_reason": observation.unavailable_reason,
        "disk_usage": serialize_disk_usage(observation.disk_usage),
    }


def serialize_disk_usage(snapshot: DiskUsageSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "filesystem_path": snapshot.filesystem_path,
        "total_bytes": snapshot.total_bytes,
        "used_bytes": snapshot.used_bytes,
        "free_bytes": snapshot.free_bytes,
        "unavailable_reason": snapshot.unavailable_reason,
    }


def _now_epoch_s() -> float:
    return datetime.now(timezone.utc).timestamp()


def _max_optional(current: int | None, value: int) -> int:
    if current is None:
        return value
    return max(current, value)


def _safe_diagnostic(message: str) -> None:
    try:
        print(message, file=sys.__stderr__)
    except BaseException:
        pass
