from runsentry.observation import (
    ProcessIdentity,
    ProcessObservation,
    ResourceSnapshot,
    SwapSnapshot,
    SystemMemorySnapshot,
)
from runsentry.output import StreamActivitySnapshot
from runsentry.watch import DiskUsageSnapshot, WatchedPathObservation


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
