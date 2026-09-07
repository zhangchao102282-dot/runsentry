from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

try:
    import psutil
except ModuleNotFoundError:
    psutil = None  # type: ignore[assignment]

DEFAULT_RESOURCE_SAMPLE_INTERVAL_S = 1.0


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time_epoch_s: float | None


@dataclass(frozen=True)
class ProcessObservation:
    identity: ProcessIdentity
    role: str
    alive: bool
    status: str | None
    cpu_percent: float | None
    rss_bytes: int | None
    access_denied: bool = False
    zombie: bool = False
    disappeared: bool = False
    pid_reused: bool = False


@dataclass(frozen=True)
class SystemMemorySnapshot:
    total_bytes: int | None
    available_bytes: int | None
    used_bytes: int | None
    percent: float | None
    unavailable: bool = False


@dataclass(frozen=True)
class SwapSnapshot:
    total_bytes: int | None
    used_bytes: int | None
    free_bytes: int | None
    percent: float | None
    unavailable: bool = False


@dataclass(frozen=True)
class ResourceSnapshot:
    observed_monotonic_s: float
    elapsed_s: float
    root_identity: ProcessIdentity
    root_observation: ProcessObservation
    current_observable_process_count: int
    current_alive_known_process_count: int
    observable_descendant_count: int
    tree_cpu_percent: float | None
    tree_rss_bytes: int | None
    tree_rss_partial: bool
    current_observable_members: tuple[ProcessIdentity, ...]
    known_descendants: tuple[ProcessIdentity, ...]
    disappeared_descendants: tuple[ProcessIdentity, ...]
    inaccessible_process_count: int
    pid_reuse_observed: bool
    observation_complete: bool
    unavailable_reasons: tuple[str, ...]
    system_memory: SystemMemorySnapshot
    swap: SwapSnapshot


@dataclass
class ProcessRegistry:
    descendants: dict[int, ProcessIdentity] = field(default_factory=dict)
    disappeared_descendants: dict[int, ProcessIdentity] = field(default_factory=dict)
    pid_reuse_observed: bool = False

    def remember_descendant(self, identity: ProcessIdentity) -> None:
        self.descendants[identity.pid] = identity
        self.disappeared_descendants.pop(identity.pid, None)

    def mark_disappeared(self, identity: ProcessIdentity) -> None:
        self.disappeared_descendants[identity.pid] = identity


class ProcessResourceObserver:
    def __init__(
        self,
        root_pid: int,
        launch_monotonic_s: float,
        root_create_time_epoch_s: float | None = None,
    ) -> None:
        self.root_identity = ProcessIdentity(root_pid, root_create_time_epoch_s)
        self.launch_monotonic_s = launch_monotonic_s
        self.registry = ProcessRegistry()
        self.latest_snapshot: ResourceSnapshot | None = None
        self._cpu_primed_pids: set[int] = set()

    def sample(self) -> ResourceSnapshot:
        now = time.monotonic()
        if psutil is None:
            snapshot = _unavailable_snapshot(
                root_identity=self.root_identity,
                launch_monotonic_s=self.launch_monotonic_s,
                observed_monotonic_s=now,
                reason="psutil_unavailable",
            )
            self.latest_snapshot = snapshot
            return snapshot

        observations: list[ProcessObservation] = []
        reasons: list[str] = []

        root_lookup = _lookup_process_for_identity(self.root_identity)
        if root_lookup.state == "missing":
            root_observation = ProcessObservation(
                identity=self.root_identity,
                role="root",
                alive=False,
                status=None,
                cpu_percent=None,
                rss_bytes=None,
                disappeared=True,
            )
            reasons.append("root_not_observable")
        elif root_lookup.state == "pid_reused":
            root_observation = ProcessObservation(
                identity=self.root_identity,
                role="root",
                alive=False,
                status=None,
                cpu_percent=None,
                rss_bytes=None,
                pid_reused=True,
            )
            reasons.append("root_pid_reused")
        elif root_lookup.state == "access_denied":
            root_observation = ProcessObservation(
                identity=self.root_identity,
                role="root",
                alive=True,
                status=None,
                cpu_percent=None,
                rss_bytes=None,
                access_denied=True,
            )
            observations.append(root_observation)
            reasons.append("root_access_denied")
        else:
            root_process = root_lookup.process
            root_observation = _observe_process(
                root_process,
                self.root_identity,
                "root",
                self._cpu_primed_pids,
            )
            observations.append(root_observation)
            descendant_discovery_reason = self._discover_descendants(root_process)
            if descendant_discovery_reason is not None:
                reasons.append(descendant_discovery_reason)

        for identity in list(self.registry.descendants.values()):
            lookup = _lookup_process_for_identity(identity)
            if lookup.state == "missing":
                self.registry.mark_disappeared(identity)
                continue
            if lookup.state == "pid_reused":
                self.registry.pid_reuse_observed = True
                self.registry.mark_disappeared(identity)
                continue
            if lookup.state == "access_denied":
                observations.append(
                    ProcessObservation(
                        identity=identity,
                        role="descendant",
                        alive=True,
                        status=None,
                        cpu_percent=None,
                        rss_bytes=None,
                        access_denied=True,
                    )
                )
                continue
            process = lookup.process
            observations.append(
                _observe_process(process, identity, "descendant", self._cpu_primed_pids)
            )

        observed_members = tuple(
            observation.identity
            for observation in observations
            if observation.alive and not observation.access_denied and not observation.pid_reused
        )
        inaccessible_count = sum(1 for observation in observations if observation.access_denied)
        rss_values = [
            observation.rss_bytes
            for observation in observations
            if observation.alive and observation.rss_bytes is not None
        ]
        cpu_values = [
            observation.cpu_percent
            for observation in observations
            if observation.alive and observation.cpu_percent is not None
        ]
        tree_rss_partial = any(
            observation.alive and observation.rss_bytes is None for observation in observations
        )
        tree_cpu_percent = sum(cpu_values) if cpu_values else None
        tree_rss_bytes = sum(rss_values) if rss_values else None
        if inaccessible_count:
            reasons.append("process_metrics_partial")

        snapshot = ResourceSnapshot(
            observed_monotonic_s=now,
            elapsed_s=max(0.0, now - self.launch_monotonic_s),
            root_identity=self.root_identity,
            root_observation=root_observation,
            current_observable_process_count=len(observed_members),
            current_alive_known_process_count=sum(
                1
                for observation in observations
                if observation.alive and not observation.pid_reused
            ),
            observable_descendant_count=sum(
                1
                for observation in observations
                if observation.role == "descendant"
                and observation.alive
                and not observation.access_denied
                and not observation.pid_reused
            ),
            tree_cpu_percent=tree_cpu_percent,
            tree_rss_bytes=tree_rss_bytes,
            tree_rss_partial=tree_rss_partial,
            current_observable_members=observed_members,
            known_descendants=tuple(self.registry.descendants.values()),
            disappeared_descendants=tuple(self.registry.disappeared_descendants.values()),
            inaccessible_process_count=inaccessible_count,
            pid_reuse_observed=self.registry.pid_reuse_observed
            or root_observation.pid_reused,
            observation_complete=not reasons and not tree_rss_partial,
            unavailable_reasons=tuple(reasons),
            system_memory=_sample_memory(),
            swap=_sample_swap(),
        )
        self.latest_snapshot = snapshot
        return snapshot

    def _discover_descendants(self, root_process: Any) -> str | None:
        try:
            children = root_process.children(recursive=True)
        except psutil.NoSuchProcess:
            return "descendant_discovery_race"
        except psutil.AccessDenied:
            return "descendant_discovery_access_denied"
        except psutil.ZombieProcess:
            return "descendant_discovery_race"
        except PermissionError:
            return "descendant_discovery_access_denied"

        for child in children:
            identity = _identity_for_process(child)
            if identity is not None:
                self.registry.remember_descendant(identity)
        return None


@dataclass(frozen=True)
class _ProcessLookup:
    state: str
    process: Any | None = None


def root_create_time_for_pid(pid: int) -> float | None:
    if psutil is None:
        return None
    try:
        return float(psutil.Process(pid).create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, PermissionError):
        return None


def _identity_for_process(process: Any) -> ProcessIdentity | None:
    try:
        return ProcessIdentity(pid=int(process.pid), create_time_epoch_s=float(process.create_time()))
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, PermissionError):
        return None


def _lookup_process_for_identity(identity: ProcessIdentity) -> _ProcessLookup:
    try:
        process = psutil.Process(identity.pid)
        if identity.create_time_epoch_s is not None:
            create_time = float(process.create_time())
            if abs(create_time - identity.create_time_epoch_s) > 0.001:
                return _ProcessLookup("pid_reused")
        return _ProcessLookup("ok", process)
    except psutil.NoSuchProcess:
        return _ProcessLookup("missing")
    except psutil.AccessDenied:
        return _ProcessLookup("access_denied")
    except psutil.ZombieProcess:
        return _ProcessLookup("missing")
    except PermissionError:
        return _ProcessLookup("access_denied")


def _observe_process(
    process: Any,
    identity: ProcessIdentity,
    role: str,
    cpu_primed_pids: set[int],
) -> ProcessObservation:
    try:
        status = process.status()
        zombie = status == getattr(psutil, "STATUS_ZOMBIE", "zombie")
        raw_cpu_percent = process.cpu_percent(interval=None)
        if identity.pid in cpu_primed_pids:
            cpu_percent = raw_cpu_percent
        else:
            cpu_primed_pids.add(identity.pid)
            cpu_percent = None
        rss_bytes = int(process.memory_info().rss)
        return ProcessObservation(
            identity=identity,
            role=role,
            alive=True,
            status=status,
            cpu_percent=cpu_percent,
            rss_bytes=rss_bytes,
            zombie=zombie,
        )
    except psutil.NoSuchProcess:
        return ProcessObservation(
            identity=identity,
            role=role,
            alive=False,
            status=None,
            cpu_percent=None,
            rss_bytes=None,
            disappeared=True,
        )
    except psutil.ZombieProcess:
        return ProcessObservation(
            identity=identity,
            role=role,
            alive=True,
            status=getattr(psutil, "STATUS_ZOMBIE", "zombie"),
            cpu_percent=None,
            rss_bytes=None,
            zombie=True,
        )
    except psutil.AccessDenied:
        return ProcessObservation(
            identity=identity,
            role=role,
            alive=True,
            status=None,
            cpu_percent=None,
            rss_bytes=None,
            access_denied=True,
        )
    except PermissionError:
        return ProcessObservation(
            identity=identity,
            role=role,
            alive=True,
            status=None,
            cpu_percent=None,
            rss_bytes=None,
            access_denied=True,
        )


def _sample_memory() -> SystemMemorySnapshot:
    try:
        memory = psutil.virtual_memory()
        return SystemMemorySnapshot(
            total_bytes=int(memory.total),
            available_bytes=int(memory.available),
            used_bytes=int(memory.used),
            percent=float(memory.percent),
        )
    except Exception:
        return SystemMemorySnapshot(
            total_bytes=None,
            available_bytes=None,
            used_bytes=None,
            percent=None,
            unavailable=True,
        )


def _sample_swap() -> SwapSnapshot:
    try:
        swap = psutil.swap_memory()
        return SwapSnapshot(
            total_bytes=int(swap.total),
            used_bytes=int(swap.used),
            free_bytes=int(swap.free),
            percent=float(swap.percent),
        )
    except Exception:
        return SwapSnapshot(
            total_bytes=None,
            used_bytes=None,
            free_bytes=None,
            percent=None,
            unavailable=True,
        )


def _unavailable_snapshot(
    root_identity: ProcessIdentity,
    launch_monotonic_s: float,
    observed_monotonic_s: float,
    reason: str,
) -> ResourceSnapshot:
    root_observation = ProcessObservation(
        identity=root_identity,
        role="root",
        alive=False,
        status=None,
        cpu_percent=None,
        rss_bytes=None,
    )
    return ResourceSnapshot(
        observed_monotonic_s=observed_monotonic_s,
        elapsed_s=max(0.0, observed_monotonic_s - launch_monotonic_s),
        root_identity=root_identity,
        root_observation=root_observation,
        current_observable_process_count=0,
        current_alive_known_process_count=0,
        observable_descendant_count=0,
        tree_cpu_percent=None,
        tree_rss_bytes=None,
        tree_rss_partial=True,
        current_observable_members=(),
        known_descendants=(),
        disappeared_descendants=(),
        inaccessible_process_count=0,
        pid_reuse_observed=False,
        observation_complete=False,
        unavailable_reasons=(reason,),
        system_memory=SystemMemorySnapshot(None, None, None, None, unavailable=True),
        swap=SwapSnapshot(None, None, None, None, unavailable=True),
    )
