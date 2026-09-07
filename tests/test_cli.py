import json
import os
import signal
import subprocess
import sys
import time

import pytest

from runsentry.cli import main
from runsentry.execution import (
    EXIT_COMMAND_NOT_FOUND,
    EXIT_SIGINT,
    EXIT_USAGE,
)


def test_cli_help_returns_success(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "runsentry" in captured.out
    assert "run" in captured.out


def test_python_module_help_returns_success() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "runsentry", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "runsentry" in result.stdout


def test_exit_zero_propagates() -> None:
    result = subprocess.run(
        _runsentry_run_args([sys.executable, "-c", "raise SystemExit(0)"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_nonzero_exit_propagates() -> None:
    result = subprocess.run(
        _runsentry_run_args([sys.executable, "-c", "raise SystemExit(7)"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 7


def test_stdout_is_visible_through_inheritance() -> None:
    result = subprocess.run(
        _runsentry_run_args([sys.executable, "-c", "print('RS_P0_003_STDOUT')"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "RS_P0_003_STDOUT" in result.stdout


def test_missing_command_returns_127() -> None:
    result = subprocess.run(
        _runsentry_run_args(["runsentry-definitely-not-a-real-command-003"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == EXIT_COMMAND_NOT_FOUND
    assert "command not found" in result.stderr


def test_missing_boundary_is_rejected() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "runsentry", "run", sys.executable, "-c", "print('no')"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == EXIT_USAGE
    assert "requires an explicit --" in result.stderr


def test_empty_command_after_boundary_is_rejected() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "runsentry", "run", "--"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == EXIT_USAGE
    assert "requires a command after --" in result.stderr


def test_invalid_interval_is_rejected_before_child_launch() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runsentry",
            "run",
            "--interval",
            "0.5",
            "--",
            sys.executable,
            "-c",
            "print('invalid interval child should not run')",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == EXIT_USAGE
    assert "must be between 1.0 and 60.0" in result.stderr
    assert "invalid interval child should not run" not in result.stdout


def test_name_parsing_does_not_leak_to_child_argv(tmp_path) -> None:
    argv_path = tmp_path / "argv.json"
    result = subprocess.run(
        _argv_writer_command(argv_path, ["--name", "inner", "--watch", "foo"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(argv_path.read_text()) == ["--name", "inner", "--watch", "foo"]


def test_argv_preservation_with_literal_special_arguments(tmp_path) -> None:
    argv_path = tmp_path / "argv.json"
    child_args = [
        "space value",
        '"quoted"',
        "--dashy",
        "unicaf\u00e9",
        "*",
        "$HOME",
        ";",
        "|",
    ]
    result = subprocess.run(
        _argv_writer_command(argv_path, child_args),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(argv_path.read_text()) == child_args


def test_ctrl_c_waits_for_child_interrupt_without_manual_double_forwarding(tmp_path) -> None:
    ready_path = tmp_path / "ready.txt"
    child = (
        "import pathlib, signal, sys, time\n"
        "def handle(signum, frame):\n"
        "    raise SystemExit(130)\n"
        "signal.signal(signal.SIGINT, handle)\n"
        "pathlib.Path(sys.argv[1]).write_text('ready')\n"
        "time.sleep(30)\n"
    )
    process = subprocess.Popen(
        _runsentry_run_args([sys.executable, "-c", child, str(ready_path)]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        _wait_for_path(ready_path)
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
        stdout, stderr = process.communicate(timeout=8)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert process.returncode == EXIT_SIGINT
    assert "interrupted; child is still running" not in stderr
    assert stdout == ""


def _runsentry_run_args(child_argv: list[str]) -> list[str]:
    return [sys.executable, "-m", "runsentry", "run", "--name", "outer", "--", *child_argv]


def _wait_for_path(path, timeout_s: float = 5.0) -> None:
    deadline_s = time.monotonic() + timeout_s
    while time.monotonic() < deadline_s:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")


def _argv_writer_command(argv_path, child_args: list[str]) -> list[str]:
    script = (
        "import json, pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))"
    )
    return _runsentry_run_args([sys.executable, "-c", script, str(argv_path), *child_args])
