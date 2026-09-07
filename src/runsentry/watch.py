from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskUsageSnapshot:
    filesystem_path: str | None
    total_bytes: int | None
    used_bytes: int | None
    free_bytes: int | None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class WatchedPathObservation:
    original_path: str
    absolute_path: str
    exists: bool
    kind: str
    size_bytes: int | None
    aggregate_size_bytes: int | None
    file_count: int | None
    latest_mtime_epoch_s: float | None
    device_id: int | None
    inode: int | None
    changed_since_previous_sample: bool
    size_delta_bytes: int | None
    mtime_changed_since_previous_sample: bool | None
    replaced_since_previous_sample: bool | None
    observation_partial: bool = False
    unavailable_reason: str | None = None
    disk_usage: DiskUsageSnapshot | None = None

    @property
    def measured_size_bytes(self) -> int | None:
        if self.kind == "file":
            return self.size_bytes
        if self.kind == "directory":
            return self.aggregate_size_bytes
        return None


class PathObserver:
    def __init__(self, watch_paths: list[str], cwd: str | None = None) -> None:
        self.watch_paths = tuple(watch_paths)
        self.cwd = Path(cwd or os.getcwd())
        self.previous_observations: dict[str, WatchedPathObservation] = {}
        self.latest_observations: tuple[WatchedPathObservation, ...] = ()

    def sample(self) -> tuple[WatchedPathObservation, ...]:
        observations: list[WatchedPathObservation] = []
        for original_path in self.watch_paths:
            observation = _observe_path(
                original_path,
                self._absolute_path(original_path),
                self.previous_observations.get(original_path),
            )
            observations.append(observation)
            self.previous_observations[original_path] = observation
        self.latest_observations = tuple(observations)
        return self.latest_observations

    def _absolute_path(self, path: str) -> Path:
        expanded = Path(path).expanduser()
        if expanded.is_absolute():
            return expanded
        return self.cwd / expanded


def _observe_path(
    original_path: str,
    absolute_path: Path,
    previous: WatchedPathObservation | None,
) -> WatchedPathObservation:
    disk_usage = _disk_usage_for_path(absolute_path)
    try:
        stat_result = absolute_path.stat()
    except FileNotFoundError:
        return _with_delta(
            WatchedPathObservation(
                original_path=original_path,
                absolute_path=str(absolute_path),
                exists=False,
                kind="missing",
                size_bytes=None,
                aggregate_size_bytes=None,
                file_count=None,
                latest_mtime_epoch_s=None,
                device_id=None,
                inode=None,
                changed_since_previous_sample=False,
                size_delta_bytes=None,
                mtime_changed_since_previous_sample=None,
                replaced_since_previous_sample=None,
                disk_usage=disk_usage,
            ),
            previous,
        )
    except PermissionError:
        return _with_delta(
            _unavailable_observation(
                original_path,
                absolute_path,
                kind="inaccessible",
                reason="permission_denied",
                disk_usage=disk_usage,
            ),
            previous,
        )
    except OSError as exc:
        return _with_delta(
            _unavailable_observation(
                original_path,
                absolute_path,
                kind="inaccessible",
                reason=f"os_error:{exc.errno}",
                disk_usage=disk_usage,
            ),
            previous,
        )

    identity = (int(stat_result.st_dev), int(stat_result.st_ino))
    latest_mtime = float(stat_result.st_mtime)

    if absolute_path.is_file():
        return _with_delta(
            WatchedPathObservation(
                original_path=original_path,
                absolute_path=str(absolute_path),
                exists=True,
                kind="file",
                size_bytes=int(stat_result.st_size),
                aggregate_size_bytes=None,
                file_count=None,
                latest_mtime_epoch_s=latest_mtime,
                device_id=identity[0],
                inode=identity[1],
                changed_since_previous_sample=False,
                size_delta_bytes=None,
                mtime_changed_since_previous_sample=None,
                replaced_since_previous_sample=None,
                disk_usage=disk_usage,
            ),
            previous,
        )

    if absolute_path.is_dir():
        scan = _scan_directory(absolute_path)
        return _with_delta(
            WatchedPathObservation(
                original_path=original_path,
                absolute_path=str(absolute_path),
                exists=True,
                kind="directory",
                size_bytes=None,
                aggregate_size_bytes=scan.aggregate_size_bytes,
                file_count=scan.file_count,
                latest_mtime_epoch_s=max(latest_mtime, scan.latest_mtime_epoch_s or latest_mtime),
                device_id=identity[0],
                inode=identity[1],
                changed_since_previous_sample=False,
                size_delta_bytes=None,
                mtime_changed_since_previous_sample=None,
                replaced_since_previous_sample=None,
                observation_partial=scan.partial,
                unavailable_reason=scan.unavailable_reason,
                disk_usage=disk_usage,
            ),
            previous,
        )

    return _with_delta(
        WatchedPathObservation(
            original_path=original_path,
            absolute_path=str(absolute_path),
            exists=True,
            kind="other",
            size_bytes=None,
            aggregate_size_bytes=None,
            file_count=None,
            latest_mtime_epoch_s=latest_mtime,
            device_id=identity[0],
            inode=identity[1],
            changed_since_previous_sample=False,
            size_delta_bytes=None,
            mtime_changed_since_previous_sample=None,
            replaced_since_previous_sample=None,
            disk_usage=disk_usage,
        ),
        previous,
    )


@dataclass(frozen=True)
class _DirectoryScan:
    aggregate_size_bytes: int
    file_count: int
    latest_mtime_epoch_s: float | None
    partial: bool
    unavailable_reason: str | None


def _scan_directory(path: Path) -> _DirectoryScan:
    total_size = 0
    file_count = 0
    latest_mtime: float | None = None
    partial = False
    reason: str | None = None
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        partial = True
                        reason = reason or "directory_entry_race"
                        continue
                    except PermissionError:
                        partial = True
                        reason = reason or "permission_denied"
                        continue
                    except OSError as exc:
                        partial = True
                        reason = reason or f"os_error:{exc.errno}"
                        continue

                    entry_mtime = float(entry_stat.st_mtime)
                    latest_mtime = (
                        entry_mtime
                        if latest_mtime is None
                        else max(latest_mtime, entry_mtime)
                    )
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total_size += int(entry_stat.st_size)
                        file_count += 1
        except FileNotFoundError:
            partial = True
            reason = reason or "directory_race"
        except PermissionError:
            partial = True
            reason = reason or "permission_denied"
        except OSError as exc:
            partial = True
            reason = reason or f"os_error:{exc.errno}"

    return _DirectoryScan(total_size, file_count, latest_mtime, partial, reason)


def _with_delta(
    current: WatchedPathObservation,
    previous: WatchedPathObservation | None,
) -> WatchedPathObservation:
    if previous is None:
        return current

    previous_size = previous.measured_size_bytes
    current_size = current.measured_size_bytes
    size_delta = (
        current_size - previous_size
        if current_size is not None and previous_size is not None
        else None
    )
    mtime_changed = (
        current.latest_mtime_epoch_s != previous.latest_mtime_epoch_s
        if current.latest_mtime_epoch_s is not None
        and previous.latest_mtime_epoch_s is not None
        else None
    )
    replaced = (
        (current.device_id, current.inode) != (previous.device_id, previous.inode)
        if current.device_id is not None
        and current.inode is not None
        and previous.device_id is not None
        and previous.inode is not None
        else None
    )
    changed = (
        current.exists != previous.exists
        or current.kind != previous.kind
        or size_delta not in (None, 0)
        or mtime_changed is True
        or replaced is True
    )
    return WatchedPathObservation(
        original_path=current.original_path,
        absolute_path=current.absolute_path,
        exists=current.exists,
        kind=current.kind,
        size_bytes=current.size_bytes,
        aggregate_size_bytes=current.aggregate_size_bytes,
        file_count=current.file_count,
        latest_mtime_epoch_s=current.latest_mtime_epoch_s,
        device_id=current.device_id,
        inode=current.inode,
        changed_since_previous_sample=changed,
        size_delta_bytes=size_delta,
        mtime_changed_since_previous_sample=mtime_changed,
        replaced_since_previous_sample=replaced,
        observation_partial=current.observation_partial,
        unavailable_reason=current.unavailable_reason,
        disk_usage=current.disk_usage,
    )


def _unavailable_observation(
    original_path: str,
    absolute_path: Path,
    kind: str,
    reason: str,
    disk_usage: DiskUsageSnapshot | None,
) -> WatchedPathObservation:
    return WatchedPathObservation(
        original_path=original_path,
        absolute_path=str(absolute_path),
        exists=False,
        kind=kind,
        size_bytes=None,
        aggregate_size_bytes=None,
        file_count=None,
        latest_mtime_epoch_s=None,
        device_id=None,
        inode=None,
        changed_since_previous_sample=False,
        size_delta_bytes=None,
        mtime_changed_since_previous_sample=None,
        replaced_since_previous_sample=None,
        observation_partial=True,
        unavailable_reason=reason,
        disk_usage=disk_usage,
    )


def _disk_usage_for_path(path: Path) -> DiskUsageSnapshot:
    ancestor = _nearest_existing_ancestor(path)
    if ancestor is None:
        return DiskUsageSnapshot(None, None, None, None, "no_existing_ancestor")
    try:
        usage = shutil.disk_usage(ancestor)
    except PermissionError:
        return DiskUsageSnapshot(str(ancestor), None, None, None, "permission_denied")
    except OSError as exc:
        return DiskUsageSnapshot(str(ancestor), None, None, None, f"os_error:{exc.errno}")
    return DiskUsageSnapshot(
        filesystem_path=str(ancestor),
        total_bytes=int(usage.total),
        used_bytes=int(usage.used),
        free_bytes=int(usage.free),
    )


def _nearest_existing_ancestor(path: Path) -> Path | None:
    current = path
    while True:
        try:
            if current.exists():
                return current
        except PermissionError:
            return current
        except OSError:
            return None

        parent = current.parent
        if parent == current:
            return None
        current = parent
