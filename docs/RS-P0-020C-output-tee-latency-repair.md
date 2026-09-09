# RS-P0-020C Output Tee Latency Repair

Date: 2026-09-09

## Root Cause

RunSentry's output drainer used `self.source.read(READ_CHUNK_SIZE)` where
`READ_CHUNK_SIZE` is 64 KiB. For `subprocess.PIPE`, `self.source` is a buffered binary
file object. Its `read(size)` call may wait until the requested size is satisfied, EOF is
seen, or the internal buffering conditions are met.

That meant small flushed child writes could remain invisible until the child exited or
enough bytes accumulated. The visual demo exposed this because a child process printing
short flushed progress lines every second appeared as one final burst.

## Reproduction

Minimal child behavior:

```python
import sys
import time

for index in range(4):
    print(f"tick {index}", flush=True)
    time.sleep(1)
```

Before the repair, wrapping that child with RunSentry produced all four lines at process
completion:

```text
4.21s tick 0
4.21s tick 1
4.21s tick 2
4.21s tick 3
DELTAS=0.00,0.00,0.00
```

## Runtime Change

Changed `src/runsentry/output.py` so `StreamDrainer` reads real file descriptors with:

```python
os.read(fd, READ_CHUNK_SIZE)
```

instead of:

```python
self.source.read(READ_CHUNK_SIZE)
```

For file-like objects without a usable file descriptor, the drainer keeps the previous
`.read(READ_CHUNK_SIZE)` fallback. This preserves unit-test support for `io.BytesIO`.

## Preserved Semantics

- Byte forwarding remains binary and byte-preserving.
- stdout and stderr remain separate streams.
- stdout/stderr content is still not retained.
- Activity byte counters and timestamps are still updated from forwarded chunks.
- Draining after child exit is preserved.
- `shell=False` launch behavior is unchanged.
- SIGINT handling is unchanged.
- Exit-code propagation is unchanged.
- Cross-stream ordering remains not guaranteed.

## Regression Coverage

Added `test_small_flushed_stdout_is_forwarded_before_child_exit`.

The test launches a child that prints one line, flushes, sleeps for 1.5 seconds, then
prints another line. It asserts that the first line is visible in less than one second
and while the child is still running.

## Demo Cleanup

Removed the RS-P0-020B invisible padding workaround from:

- `examples/demo_long_job.py`
- `examples/demo_terminal_flow.sh`

The demo keeps normal `flush=True` calls and `python -u` in the recording flow.

## Validation

Commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/runsentry --help
.venv/bin/runsentry run --help
bash examples/demo_terminal_flow.sh
```

Additional timing check after the repair showed progress lines arriving incrementally,
with roughly two seconds between demo steps, without artificial pipe-filling bytes.

Results:

- `tests/test_output.py`: PASS, 14 passed.
- `.venv/bin/python -m pytest -q`: PASS, 107 passed, 3 skipped.
- `.venv/bin/runsentry --help`: PASS.
- `.venv/bin/runsentry run --help`: PASS.
- `bash examples/demo_terminal_flow.sh`: PASS.
- Demo timing check: PASS, step deltas approximately `2.00,2.01,2.13,2.01,2.00`
  seconds.
- Demo final health: `COMPLETE`.
- Demo exit code: 0.
- Demo telemetry: `/tmp/rs-demo/runs/20260909T211512Z-ae152264813d/telemetry.jsonl`.
- Demo summary: `/tmp/rs-demo/runs/20260909T211512Z-ae152264813d/summary.json`.
- Demo watched file: 7 deterministic lines, 169 bytes.
