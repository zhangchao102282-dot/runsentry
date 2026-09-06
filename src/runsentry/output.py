from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import BinaryIO, TextIO

READ_CHUNK_SIZE = 64 * 1024


@dataclass
class StreamActivity:
    name: str
    total_bytes: int = 0
    total_chunks: int = 0
    first_activity_monotonic_s: float | None = None
    last_activity_monotonic_s: float | None = None
    read_error: str | None = None
    display_error: str | None = None
    eof: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_chunk(self, size: int, now: float) -> None:
        with self._lock:
            self.total_bytes += size
            self.total_chunks += 1
            if self.first_activity_monotonic_s is None:
                self.first_activity_monotonic_s = now
            self.last_activity_monotonic_s = now

    def record_read_error(self, exc: BaseException) -> None:
        with self._lock:
            self.read_error = f"{type(exc).__name__}: {exc}"

    def record_display_error(self, exc: BaseException) -> None:
        with self._lock:
            if self.display_error is None:
                self.display_error = f"{type(exc).__name__}: {exc}"

    def record_eof(self) -> None:
        with self._lock:
            self.eof = True

    def snapshot(self) -> "StreamActivitySnapshot":
        with self._lock:
            return StreamActivitySnapshot(
                name=self.name,
                total_bytes=self.total_bytes,
                total_chunks=self.total_chunks,
                first_activity_monotonic_s=self.first_activity_monotonic_s,
                last_activity_monotonic_s=self.last_activity_monotonic_s,
                read_error=self.read_error,
                display_error=self.display_error,
                eof=self.eof,
            )


@dataclass(frozen=True)
class StreamActivitySnapshot:
    name: str
    total_bytes: int
    total_chunks: int
    first_activity_monotonic_s: float | None
    last_activity_monotonic_s: float | None
    read_error: str | None
    display_error: str | None
    eof: bool


class BinaryOutputSink:
    def __init__(self, stream: TextIO | BinaryIO) -> None:
        self._stream = stream
        self._binary_stream = getattr(stream, "buffer", stream)

    def write(self, data: bytes) -> None:
        try:
            self._binary_stream.write(data)
        except TypeError:
            self._stream.write(data.decode("utf-8", errors="replace"))

    def flush(self) -> None:
        self._stream.flush()


@dataclass
class StreamDrainer:
    name: str
    source: BinaryIO
    sink: BinaryOutputSink
    activity: StreamActivity = field(init=False)
    _thread: threading.Thread = field(init=False, repr=False)
    _forwarding_enabled: bool = field(default=True, init=False, repr=False)

    def __post_init__(self) -> None:
        self.activity = StreamActivity(name=self.name)
        self._thread = threading.Thread(
            target=self._run,
            name=f"runsentry-{self.name}-drainer",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float | None = None) -> bool:
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        try:
            while True:
                chunk = self.source.read(READ_CHUNK_SIZE)
                if not chunk:
                    self.activity.record_eof()
                    return

                self.activity.record_chunk(len(chunk), time.monotonic())
                if self._forwarding_enabled:
                    self._write_chunk(chunk)
        except BaseException as exc:
            self.activity.record_read_error(exc)

    def _write_chunk(self, chunk: bytes) -> None:
        try:
            self.sink.write(chunk)
            self.sink.flush()
        except BaseException as exc:
            self.activity.record_display_error(exc)
            self._forwarding_enabled = False


@dataclass
class OutputPump:
    stdout: StreamDrainer
    stderr: StreamDrainer

    def start(self) -> None:
        self.stdout.start()
        self.stderr.start()

    def join(self, timeout_per_stream_s: float = 5.0) -> bool:
        stdout_done = self.stdout.join(timeout=timeout_per_stream_s)
        stderr_done = self.stderr.join(timeout=timeout_per_stream_s)
        return stdout_done and stderr_done

    def stdout_snapshot(self) -> StreamActivitySnapshot:
        return self.stdout.activity.snapshot()

    def stderr_snapshot(self) -> StreamActivitySnapshot:
        return self.stderr.activity.snapshot()


def make_output_pump(stdout_source: BinaryIO, stderr_source: BinaryIO) -> OutputPump:
    return OutputPump(
        stdout=StreamDrainer("stdout", stdout_source, BinaryOutputSink(sys.stdout)),
        stderr=StreamDrainer("stderr", stderr_source, BinaryOutputSink(sys.stderr)),
    )
