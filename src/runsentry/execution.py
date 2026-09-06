from __future__ import annotations

import errno
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from .output import OutputPump, StreamActivitySnapshot, make_output_pump

EXIT_USAGE = 2
EXIT_PERMISSION_DENIED = 126
EXIT_COMMAND_NOT_FOUND = 127
EXIT_INTERNAL_ERROR = 1
EXIT_SIGINT = 130


@dataclass(frozen=True)
class RunSpec:
    name: str | None
    argv: list[str]


@dataclass(frozen=True)
class LaunchInfo:
    name: str | None
    argv: list[str]
    pid: int
    start_monotonic_s: float
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


@dataclass(frozen=True)
class _WaitOutcome:
    exit_code: int
    restore_sigint_handler: object | None = None


@dataclass(frozen=True)
class _RunningProcess:
    info: LaunchInfo
    process: subprocess.Popen[bytes]
    output_pump: OutputPump


def launch_process(run_spec: RunSpec) -> _RunningProcess:
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
    )
    if process.stdout is None or process.stderr is None:
        raise LaunchError("could not create child output pipes", EXIT_INTERNAL_ERROR)

    output_pump = make_output_pump(process.stdout, process.stderr)
    output_pump.start()
    return _RunningProcess(info=info, process=process, output_pump=output_pump)


def execute_command(run_spec: RunSpec) -> ExecutionResult:
    running = launch_process(run_spec)
    restore_sigint_handler: object | None = None
    try:
        try:
            wait_outcome = wait_for_process(running.process)
            restore_sigint_handler = wait_outcome.restore_sigint_handler
            return _finish_execution(running, wait_outcome.exit_code)
        except KeyboardInterrupt:
            restore_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
            _handle_keyboard_interrupt(running.process)
            return _finish_execution(running, EXIT_SIGINT)
    finally:
        if restore_sigint_handler is not None:
            signal.signal(signal.SIGINT, restore_sigint_handler)


def _finish_execution(running: _RunningProcess, exit_code: int) -> ExecutionResult:
    output_drained = running.output_pump.join()
    _report_output_failures(running.output_pump)
    return ExecutionResult(
        exit_code=exit_code,
        launch_info=LaunchInfo(
            name=running.info.name,
            argv=running.info.argv,
            pid=running.info.pid,
            start_monotonic_s=running.info.start_monotonic_s,
            returncode=running.process.returncode,
        ),
        stdout_activity=running.output_pump.stdout_snapshot(),
        stderr_activity=running.output_pump.stderr_snapshot(),
        output_drained=output_drained,
    )


def wait_for_process(process: subprocess.Popen[bytes]) -> _WaitOutcome:
    try:
        return _WaitOutcome(_return_code_to_exit_code(process.wait()))
    except KeyboardInterrupt:
        restore_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        return _WaitOutcome(
            _handle_keyboard_interrupt(process),
            restore_sigint_handler=restore_handler,
        )


def _handle_keyboard_interrupt(process: subprocess.Popen[bytes]) -> int:
    if process.poll() is not None:
        return EXIT_SIGINT

    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        print(
            "runsentry: interrupted; child is still running and was not killed.",
            file=sys.stderr,
        )
    return EXIT_SIGINT


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
