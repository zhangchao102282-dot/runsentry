import io
import os
import signal
import subprocess
import sys
import time

from runsentry.execution import EXIT_SIGINT, RunSpec, execute_command
from runsentry.output import READ_CHUNK_SIZE, BinaryOutputSink, StreamDrainer


def test_stdout_forwarding() -> None:
    result = subprocess.run(
        _runsentry_args(["print('RS_P0_004_STDOUT')"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "RS_P0_004_STDOUT" in result.stdout


def test_stderr_forwarding_and_stream_separation() -> None:
    result = subprocess.run(
        _runsentry_args(
            [
                "import sys; "
                "sys.stdout.write('RS_P0_004_OUT'); "
                "sys.stderr.write('RS_P0_004_ERR')"
            ]
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == "RS_P0_004_OUT"
    assert result.stderr == "RS_P0_004_ERR"


def test_high_volume_stdout_completes_without_deadlock() -> None:
    payload_size = READ_CHUNK_SIZE * 20
    result = subprocess.run(
        _runsentry_args([f"import os, sys; os.write(sys.stdout.fileno(), b'o' * {payload_size})"]),
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == b"o" * payload_size


def test_high_volume_stderr_completes_without_deadlock() -> None:
    payload_size = READ_CHUNK_SIZE * 20
    result = subprocess.run(
        _runsentry_args([f"import os, sys; os.write(sys.stderr.fileno(), b'e' * {payload_size})"]),
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stderr == b"e" * payload_size


def test_simultaneous_high_volume_stdout_and_stderr_complete_without_deadlock() -> None:
    payload_size = READ_CHUNK_SIZE * 20
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
        "threads = [\n"
        "    threading.Thread(target=write_all, args=(sys.stdout.fileno(), b'o')),\n"
        "    threading.Thread(target=write_all, args=(sys.stderr.fileno(), b'e')),\n"
        "]\n"
        "[thread.start() for thread in threads]\n"
        "[thread.join() for thread in threads]\n"
    )
    result = subprocess.run(
        _runsentry_args([script]),
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == b"o" * payload_size
    assert result.stderr == b"e" * payload_size


def test_no_newline_output_is_forwarded() -> None:
    result = subprocess.run(
        _runsentry_args(["import sys; sys.stdout.write('NO_NEWLINE')"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == "NO_NEWLINE"


def test_partial_chunked_output_updates_activity() -> None:
    result = execute_command(
        RunSpec(
            name="partial",
            argv=[
                sys.executable,
                "-c",
                "import sys, time; "
                "sys.stdout.write('a'); sys.stdout.flush(); "
                "time.sleep(0.05); "
                "sys.stdout.write('bc'); sys.stdout.flush()",
            ],
        )
    )
    assert result.exit_code == 0
    assert result.stdout_activity.total_bytes == 3
    assert result.stdout_activity.total_chunks >= 1
    assert result.stdout_activity.first_activity_monotonic_s is not None
    assert result.stdout_activity.last_activity_monotonic_s is not None


def test_small_flushed_stdout_is_forwarded_before_child_exit() -> None:
    script = (
        "import sys, time\n"
        "print('RS_P0_020C_FIRST', flush=True)\n"
        "time.sleep(1.5)\n"
        "print('RS_P0_020C_SECOND', flush=True)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "runsentry", "run", "--", sys.executable, "-u", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start_s = time.monotonic()
    try:
        assert process.stdout is not None
        first_line = process.stdout.readline()
        elapsed_s = time.monotonic() - start_s
        assert first_line == "RS_P0_020C_FIRST\n"
        assert elapsed_s < 1.0
        assert process.poll() is None
        stdout_tail, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert process.returncode == 0
    assert stdout_tail == "RS_P0_020C_SECOND\n"
    assert stderr == ""


def test_binary_non_utf8_output_is_forwarded_unchanged() -> None:
    expected = bytes([0xFF, 0xFE, 0x00, 0x80, 0x41])
    result = subprocess.run(
        _runsentry_args(["import os, sys; os.write(sys.stdout.fileno(), bytes([255, 254, 0, 128, 65]))"]),
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout == expected


def test_silent_child_records_zero_activity() -> None:
    result = execute_command(RunSpec(name="silent", argv=[sys.executable, "-c", "pass"]))
    assert result.exit_code == 0
    assert result.stdout_activity.total_bytes == 0
    assert result.stderr_activity.total_bytes == 0
    assert result.stdout_activity.eof
    assert result.stderr_activity.eof


def test_nonzero_child_exit_still_drains_output() -> None:
    result = subprocess.run(
        _runsentry_args(["import sys; print('TAIL_BEFORE_EXIT'); raise SystemExit(7)"]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 7
    assert "TAIL_BEFORE_EXIT" in result.stdout


def test_ctrl_c_behavior_with_output_pipes(tmp_path) -> None:
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
        [sys.executable, "-m", "runsentry", "run", "--", sys.executable, "-c", child, str(ready_path)],
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


def test_broken_forwarding_sink_does_not_stop_draining() -> None:
    class BrokenSink(BinaryOutputSink):
        def __init__(self) -> None:
            pass

        def write(self, data: bytes) -> None:
            raise BrokenPipeError("closed")

        def flush(self) -> None:
            raise AssertionError("flush should not be called after write fails")

    source = io.BytesIO(b"x" * (READ_CHUNK_SIZE * 3))
    drainer = StreamDrainer("stdout", source, BrokenSink())
    drainer.start()
    assert drainer.join(timeout=5.0)
    snapshot = drainer.activity.snapshot()
    assert snapshot.total_bytes == READ_CHUNK_SIZE * 3
    assert snapshot.total_chunks == 3
    assert snapshot.display_error is not None
    assert snapshot.eof


def test_stream_drainer_does_not_retain_output_content() -> None:
    activity_fields = set(StreamDrainer("stdout", io.BytesIO(), BinaryOutputSink(io.BytesIO())).activity.__dict__)
    assert "content" not in activity_fields
    assert "chunks" not in activity_fields
    assert "lines" not in activity_fields


def _runsentry_args(script_parts: list[str]) -> list[str]:
    return [sys.executable, "-m", "runsentry", "run", "--", sys.executable, "-c", *script_parts]


def _wait_for_path(path, timeout_s: float = 5.0) -> None:
    deadline_s = time.monotonic() + timeout_s
    while time.monotonic() < deadline_s:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")
