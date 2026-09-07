from __future__ import annotations

import errno
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from .observation import (
    DEFAULT_RESOURCE_SAMPLE_INTERVAL_S,
    ProcessResourceObserver,
    ResourceSnapshot,
    root_create_time_for_pid,
)
from .output import OutputPump, StreamActivitySnapshot, make_output_pump
from .telemetry import TelemetryInitializationError, TelemetryWriter
from .watch import PathObserver, WatchedPathObservation

EXIT_USAGE = 2
EXIT_PERMISSION_DENIED = 126
EXIT_COMMAND_NOT_FOUND = 127
EXIT_INTERNAL_ERROR = 1
EXIT_SIGINT = 130
PROCESS_WAIT_POLL_INTERVAL_S = 0.1


@dataclass(frozen=True)
class RunSpec:
    name: str | None
    argv: list[str]
    sample_interval_s: float = DEFAULT_RESOURCE_SAMPLE_INTERVAL_S
    watch_paths: list[str] | None = None
    output_dir: str | None = None


@dataclass(frozen=True)
class LaunchInfo:
    name: str | None
    argv: list[str]
    pid: int
    start_monotonic_s: float
    root_create_time_epoch_s: float | None = None
    returncode: int | None = None


class LaunchError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def run_command(run_spec: RunSpec) -> int:
    return execute_command(run_spec).exit_code


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int
    launch_info: LaunchInfo
    stdout_activity: StreamActivitySnapshot
    stderr_activity: StreamActivitySnapshot
    output_drained: bool
    latest_resource_snapshot: ResourceSnapshot | None
    latest_watched_paths: tuple[WatchedPathObservation, ...]
    run_id: str
    telemetry_path: str
    summary_path: str


@dataclass(frozen=True)
class _RunningProcess:
    run_spec: RunSpec
    info: LaunchInfo
    process: subprocess.Popen[bytes]
    output_pump: OutputPump
    observer: ProcessResourceObserver
    path_observer: PathObserver
    telemetry: TelemetryWriter


@dataclass
class _SignalState:
    sigint_observed: bool = False
    wakeup_read_fd: int | None = None
    wakeup_write_fd: int | None = None
    previous_wakeup_fd: int = -1

    def record_sigint(self, signum: int, frame: object) -> None:
        _ = signum, frame
        self.sigint_observed = True

    def install_wakeup_fd(self) -> None:
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        os.set_blocking(write_fd, False)
        self.wakeup_read_fd = read_fd
        self.wakeup_write_fd = write_fd
        self.previous_wakeup_fd = signal.set_wakeup_fd(write_fd)

    def restore_wakeup_fd(self) -> None:
        signal.set_wakeup_fd(self.previous_wakeup_fd)
        for fd in (self.wakeup_read_fd, self.wakeup_write_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.wakeup_read_fd = None
        self.wakeup_write_fd = None
        self.previous_wakeup_fd = -1

    def observed_sigint(self) -> bool:
        self._drain_wakeup_fd()
        return self.sigint_observed

    def _drain_wakeup_fd(self) -> None:
        if self.wakeup_read_fd is None:
            return
        while True:
            try:
                data = os.read(self.wakeup_read_fd, 1024)
            except BlockingIOError:
                return
            except OSError:
                return
            if not data:
                return
            if signal.SIGINT in data:
                self.sigint_observed = True


def launch_process(run_spec: RunSpec, telemetry: TelemetryWriter) -> _RunningProcess:
    try:
        process = subprocess.Popen(
            run_spec.argv,
            shell=False,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise LaunchError(
            f"command not found: {run_spec.argv[0]}",
            EXIT_COMMAND_NOT_FOUND,
        ) from exc
    except PermissionError as exc:
        raise LaunchError(
            f"permission denied: {run_spec.argv[0]}",
            EXIT_PERMISSION_DENIED,
        ) from exc
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise LaunchError(
                f"command not found: {run_spec.argv[0]}",
                EXIT_COMMAND_NOT_FOUND,
            ) from exc
        if exc.errno in {errno.EACCES, errno.EPERM}:
            raise LaunchError(
                f"permission denied: {run_spec.argv[0]}",
                EXIT_PERMISSION_DENIED,
            ) from exc
        raise LaunchError(
            f"could not launch command: {exc}",
            EXIT_INTERNAL_ERROR,
        ) from exc

    info = LaunchInfo(
        name=run_spec.name,
        argv=list(run_spec.argv),
        pid=process.pid,
        start_monotonic_s=time.monotonic(),
        root_create_time_epoch_s=root_create_time_for_pid(process.pid),
    )
    if process.stdout is None or process.stderr is None:
        raise LaunchError("could not create child output pipes", EXIT_INTERNAL_ERROR)

    output_pump = make_output_pump(process.stdout, process.stderr)
    observer = ProcessResourceObserver(
        root_pid=info.pid,
        launch_monotonic_s=info.start_monotonic_s,
        root_create_time_epoch_s=info.root_create_time_epoch_s,
    )
    path_observer = PathObserver(run_spec.watch_paths or [])
    output_pump.start()
    resource_snapshot = observer.sample()
    watched_paths = path_observer.sample()
    telemetry.write_run_started(
        name=run_spec.name,
        argv=run_spec.argv,
        root_pid=info.pid,
        root_create_time_epoch_s=info.root_create_time_epoch_s,
        watched_paths=run_spec.watch_paths or [],
        sample_interval_s=run_spec.sample_interval_s,
    )
    telemetry.write_sample(
        resource_snapshot=resource_snapshot,
        stdout_activity=output_pump.stdout_snapshot(),
        stderr_activity=output_pump.stderr_snapshot(),
        watched_paths=watched_paths,
    )
    return _RunningProcess(
        run_spec=run_spec,
        info=info,
        process=process,
        output_pump=output_pump,
        observer=observer,
        path_observer=path_observer,
        telemetry=telemetry,
    )


def execute_command(run_spec: RunSpec) -> ExecutionResult:
    try:
        telemetry = TelemetryWriter.create(run_spec.output_dir)
    except TelemetryInitializationError as exc:
        raise LaunchError(str(exc), EXIT_INTERNAL_ERROR) from exc

    signal_state = _SignalState()
    signal_state.install_wakeup_fd()
    previous_sigint_handler = signal.signal(signal.SIGINT, signal_state.record_sigint)
    try:
        running = launch_process(run_spec, telemetry)
        exit_code = wait_for_process(
            running.process,
            running.observer,
            running.path_observer,
            running.output_pump,
            running.telemetry,
            signal_state,
            sample_interval_s=running.run_spec.sample_interval_s,
        )
        if signal_state.observed_sigint():
            exit_code = EXIT_SIGINT
        return _finish_execution(running, exit_code)
    finally:
        signal.signal(signal.SIGINT, previous_sigint_handler)
        signal_state.restore_wakeup_fd()
        telemetry.close()


def _finish_execution(running: _RunningProcess, exit_code: int) -> ExecutionResult:
    latest_snapshot = running.observer.sample()
    latest_watched_paths = running.path_observer.sample()
    output_drained = running.output_pump.join()
    _report_output_failures(running.output_pump)
    stdout_activity = running.output_pump.stdout_snapshot()
    stderr_activity = running.output_pump.stderr_snapshot()
    running.telemetry.write_run_finished(
        name=running.info.name,
        argv=running.info.argv,
        exit_code=exit_code,
        child_returncode=running.process.returncode,
        output_drained=output_drained,
        resource_snapshot=latest_snapshot,
        stdout_activity=stdout_activity,
        stderr_activity=stderr_activity,
        watched_paths=latest_watched_paths,
    )
    return ExecutionResult(
        exit_code=exit_code,
        launch_info=LaunchInfo(
            name=running.info.name,
            argv=running.info.argv,
            pid=running.info.pid,
            start_monotonic_s=running.info.start_monotonic_s,
            root_create_time_epoch_s=running.info.root_create_time_epoch_s,
            returncode=running.process.returncode,
        ),
        stdout_activity=stdout_activity,
        stderr_activity=stderr_activity,
        output_drained=output_drained,
        latest_resource_snapshot=latest_snapshot,
        latest_watched_paths=latest_watched_paths,
        run_id=running.telemetry.run_id,
        telemetry_path=str(running.telemetry.paths.telemetry_path),
        summary_path=str(running.telemetry.paths.summary_path),
    )


def wait_for_process(
    process: subprocess.Popen[bytes],
    observer: ProcessResourceObserver,
    path_observer: PathObserver,
    output_pump: OutputPump,
    telemetry: TelemetryWriter,
    signal_state: _SignalState,
    sample_interval_s: float = DEFAULT_RESOURCE_SAMPLE_INTERVAL_S,
) -> int:
    interrupt_deadline_s: float | None = None
    next_sample_monotonic_s = time.monotonic() + sample_interval_s
    while True:
        now_s = time.monotonic()
        timeout_s = min(
            PROCESS_WAIT_POLL_INTERVAL_S,
            max(0.0, next_sample_monotonic_s - now_s),
        )
        if signal_state.observed_sigint():
            if process.poll() is not None:
                return EXIT_SIGINT
            if interrupt_deadline_s is None:
                interrupt_deadline_s = time.monotonic() + 5.0
            remaining_s = interrupt_deadline_s - time.monotonic()
            if remaining_s <= 0:
                _report_child_still_running_after_interrupt()
                return EXIT_SIGINT
            timeout_s = min(timeout_s, remaining_s)

        try:
            returncode = process.wait(timeout=timeout_s)
            if signal_state.observed_sigint():
                return EXIT_SIGINT
            return _return_code_to_exit_code(returncode)
        except subprocess.TimeoutExpired:
            if time.monotonic() >= next_sample_monotonic_s:
                telemetry.write_sample(
                    resource_snapshot=observer.sample(),
                    stdout_activity=output_pump.stdout_snapshot(),
                    stderr_activity=output_pump.stderr_snapshot(),
                    watched_paths=path_observer.sample(),
                )
                next_sample_monotonic_s = time.monotonic() + sample_interval_s


def _report_child_still_running_after_interrupt() -> None:
    print(
        "runsentry: interrupted; child is still running and was not killed.",
        file=sys.stderr,
    )


def _return_code_to_exit_code(returncode: int) -> int:
    if returncode < 0:
        return 128 + abs(returncode)
    return returncode


def _report_output_failures(output_pump: OutputPump) -> None:
    for activity in (
        output_pump.stdout_snapshot(),
        output_pump.stderr_snapshot(),
    ):
        if activity.read_error:
            _safe_observer_diagnostic(
                f"runsentry: {activity.name} observation failed: {activity.read_error}",
            )
        if activity.display_error:
            _safe_observer_diagnostic(
                f"runsentry: {activity.name} forwarding failed; pipe was drained without further display.",
            )


def _safe_observer_diagnostic(message: str) -> None:
    try:
        print(message, file=sys.__stderr__)
    except BaseException:
        pass
