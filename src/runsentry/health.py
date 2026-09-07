from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .observation import ResourceSnapshot
from .output import StreamActivitySnapshot
from .watch import WatchedPathObservation


class HealthState(str, Enum):
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    QUIET = "QUIET"
    SUSPECTED_STALL = "SUSPECTED_STALL"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class HealthConfig:
    starting_window_s: float = 10.0
    quiet_window_s: float = 30.0
    suspected_stall_window_s: float = 120.0
    minimal_cpu_activity_threshold: float = 1.0


DEFAULT_HEALTH_CONFIG = HealthConfig()


@dataclass(frozen=True)
class HealthAssessment:
    state: HealthState
    reason_codes: tuple[str, ...]
    terminal: bool = False


@dataclass(frozen=True)
class HealthTransition:
    elapsed_s: float
    from_state: HealthState | None
    to_state: HealthState
    reason_codes: tuple[str, ...]


@dataclass
class _PreviousFacts:
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    watched_sizes: dict[str, int | None] = field(default_factory=dict)
    watched_mtimes: dict[str, float | None] = field(default_factory=dict)
    observable_process_count: int | None = None
    observable_descendant_count: int | None = None


class HealthStateMachine:
    def __init__(self, config: HealthConfig = DEFAULT_HEALTH_CONFIG) -> None:
        self.config = config
        self.current_state: HealthState | None = None
        self.current_assessment: HealthAssessment | None = None
        self.transitions: list[HealthTransition] = []
        self._previous = _PreviousFacts()
        self._last_positive_elapsed_s: float | None = None

    def assess_sample(
        self,
        *,
        resource_snapshot: ResourceSnapshot | None,
        stdout_activity: StreamActivitySnapshot,
        stderr_activity: StreamActivitySnapshot,
        watched_paths: tuple[WatchedPathObservation, ...],
    ) -> HealthAssessment:
        elapsed_s = _elapsed(resource_snapshot)
        evidence = self._sample_evidence(
            resource_snapshot,
            stdout_activity,
            stderr_activity,
            watched_paths,
        )
        reasons: list[str] = []

        if elapsed_s < self.config.starting_window_s:
            reasons.append("starting_window")
            if evidence.positive_reason_codes:
                reasons.extend(evidence.positive_reason_codes)
                self._last_positive_elapsed_s = elapsed_s
            assessment = HealthAssessment(HealthState.STARTING, tuple(_dedupe(reasons)))
            self._record_transition(elapsed_s, assessment)
            return assessment

        if evidence.positive_reason_codes:
            self._last_positive_elapsed_s = elapsed_s
            reasons.extend(evidence.positive_reason_codes)
            assessment = HealthAssessment(HealthState.HEALTHY, tuple(_dedupe(reasons)))
            self._record_transition(elapsed_s, assessment)
            return assessment

        reasons.extend(evidence.unavailable_reason_codes)
        inactivity_duration_s = (
            elapsed_s
            if self._last_positive_elapsed_s is None
            else elapsed_s - self._last_positive_elapsed_s
        )
        if (
            inactivity_duration_s >= self.config.suspected_stall_window_s
            and evidence.output_inactive
            and evidence.cpu_low
            and evidence.watch_inactive
            and not evidence.unknown_reduces_suspicion
        ):
            reasons.append("sustained_multi_signal_inactivity")
            assessment = HealthAssessment(
                HealthState.SUSPECTED_STALL,
                tuple(_dedupe(reasons)),
            )
            self._record_transition(elapsed_s, assessment)
            return assessment

        reasons.append("insufficient_evidence_quiet")
        assessment = HealthAssessment(HealthState.QUIET, tuple(_dedupe(reasons)))
        self._record_transition(elapsed_s, assessment)
        return assessment

    def assess_finished(
        self,
        *,
        exit_code: int,
        elapsed_s: float,
        alive_known_process_count: int = 0,
    ) -> HealthAssessment:
        if exit_code == 0 and alive_known_process_count == 0:
            assessment = HealthAssessment(
                HealthState.COMPLETE,
                ("root_exit_zero",),
                terminal=True,
            )
        elif exit_code == 0:
            assessment = HealthAssessment(
                HealthState.QUIET,
                ("root_exit_zero_known_descendants_alive",),
                terminal=True,
            )
        elif exit_code == 130:
            assessment = HealthAssessment(
                HealthState.QUIET,
                ("interrupted_sigint",),
                terminal=True,
            )
        else:
            assessment = HealthAssessment(
                HealthState.FAILED,
                ("root_exit_nonzero",),
                terminal=True,
            )
        self._record_transition(elapsed_s, assessment)
        return assessment

    def transition_history(self) -> tuple[HealthTransition, ...]:
        return tuple(self.transitions)

    def _sample_evidence(
        self,
        resource_snapshot: ResourceSnapshot | None,
        stdout_activity: StreamActivitySnapshot,
        stderr_activity: StreamActivitySnapshot,
        watched_paths: tuple[WatchedPathObservation, ...],
    ) -> "_Evidence":
        positive: list[str] = []
        unavailable: list[str] = []
        unknown_reduces_suspicion = False

        output_unavailable = stdout_activity.read_error is not None or stderr_activity.read_error is not None
        output_delta = (
            stdout_activity.total_bytes > self._previous.stdout_bytes
            or stderr_activity.total_bytes > self._previous.stderr_bytes
        )
        if output_delta:
            positive.append("recent_output_activity")
        if output_unavailable:
            unavailable.append("output_observation_unavailable")
            unknown_reduces_suspicion = True
        output_inactive = not output_delta and not output_unavailable
        self._previous.stdout_bytes = stdout_activity.total_bytes
        self._previous.stderr_bytes = stderr_activity.total_bytes

        cpu_low = False
        cpu_available = False
        if resource_snapshot is None:
            unavailable.append("observation_partial")
            unknown_reduces_suspicion = True
        else:
            if not resource_snapshot.observation_complete:
                unavailable.append("observation_partial")
            cpu_values = [
                value
                for value in (
                    resource_snapshot.root_observation.cpu_percent,
                    resource_snapshot.tree_cpu_percent,
                )
                if value is not None
            ]
            if cpu_values:
                cpu_available = True
                if max(cpu_values) >= self.config.minimal_cpu_activity_threshold:
                    positive.append("recent_cpu_activity")
                else:
                    cpu_low = True
            else:
                unavailable.append("cpu_unavailable")
                unknown_reduces_suspicion = True

            previous_process_count = self._previous.observable_process_count
            previous_descendant_count = self._previous.observable_descendant_count
            if (
                previous_process_count is not None
                and previous_descendant_count is not None
                and (
                    resource_snapshot.current_observable_process_count
                    != previous_process_count
                    or resource_snapshot.observable_descendant_count
                    != previous_descendant_count
                )
            ):
                positive.append("recent_process_tree_activity")
            self._previous.observable_process_count = (
                resource_snapshot.current_observable_process_count
            )
            self._previous.observable_descendant_count = (
                resource_snapshot.observable_descendant_count
            )

        watch_inactive = False
        if watched_paths:
            watch_available = False
            any_watch_activity = False
            for observation in watched_paths:
                if observation.kind == "inaccessible" or observation.observation_partial:
                    unavailable.append("watched_path_unavailable")
                    unknown_reduces_suspicion = True
                    continue
                watch_available = True
                measured_size = observation.measured_size_bytes
                previous_size = self._previous.watched_sizes.get(
                    observation.original_path
                )
                previous_mtime = self._previous.watched_mtimes.get(
                    observation.original_path
                )
                size_changed = (
                    measured_size != previous_size
                    if measured_size is not None and previous_size is not None
                    else False
                )
                mtime_changed = (
                    observation.latest_mtime_epoch_s != previous_mtime
                    if observation.latest_mtime_epoch_s is not None
                    and previous_mtime is not None
                    else False
                )
                if observation.size_delta_bytes not in (None, 0) or size_changed or mtime_changed:
                    any_watch_activity = True
                self._previous.watched_sizes[observation.original_path] = measured_size
                self._previous.watched_mtimes[observation.original_path] = (
                    observation.latest_mtime_epoch_s
                )
            if any_watch_activity:
                positive.append("recent_watch_growth")
            watch_inactive = watch_available and not any_watch_activity
        else:
            unknown_reduces_suspicion = True

        return _Evidence(
            positive_reason_codes=tuple(_dedupe(positive)),
            unavailable_reason_codes=tuple(_dedupe(unavailable)),
            output_inactive=output_inactive,
            cpu_low=cpu_low and cpu_available,
            watch_inactive=watch_inactive,
            unknown_reduces_suspicion=unknown_reduces_suspicion,
        )

    def _record_transition(
        self,
        elapsed_s: float,
        assessment: HealthAssessment,
    ) -> None:
        if self.current_state != assessment.state:
            self.transitions.append(
                HealthTransition(
                    elapsed_s=elapsed_s,
                    from_state=self.current_state,
                    to_state=assessment.state,
                    reason_codes=assessment.reason_codes,
                )
            )
        self.current_state = assessment.state
        self.current_assessment = assessment


@dataclass(frozen=True)
class _Evidence:
    positive_reason_codes: tuple[str, ...]
    unavailable_reason_codes: tuple[str, ...]
    output_inactive: bool
    cpu_low: bool
    watch_inactive: bool
    unknown_reduces_suspicion: bool


def serialize_assessment(assessment: HealthAssessment | None) -> dict[str, object] | None:
    if assessment is None:
        return None
    return {
        "health_state": assessment.state.value,
        "reason_codes": list(assessment.reason_codes),
        "terminal": assessment.terminal,
    }


def serialize_transition_history(
    transitions: tuple[HealthTransition, ...],
) -> list[dict[str, object]]:
    return [
        {
            "elapsed_s": transition.elapsed_s,
            "from_state": (
                transition.from_state.value
                if transition.from_state is not None
                else None
            ),
            "to_state": transition.to_state.value,
            "reason_codes": list(transition.reason_codes),
        }
        for transition in transitions
    ]


def _elapsed(resource_snapshot: ResourceSnapshot | None) -> float:
    if resource_snapshot is None:
        return 0.0
    return resource_snapshot.elapsed_s


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
