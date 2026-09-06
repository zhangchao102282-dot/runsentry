# RS-P0-004 Output Observation Record

## Objective

Implement byte-level stdout/stderr observation and tee forwarding for `runsentry run -- COMMAND [ARG ...]` without adding CPU, memory, process-tree, health, watched-path, telemetry, ETA, or recovery behavior.

## Concurrency and Drain Model

RS-P0-004 launches the child with:

```text
subprocess.Popen(argv, shell=False, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
```

RunSentry starts two dedicated daemon reader threads immediately after launch:

- one thread drains child stdout
- one thread drains child stderr

Each thread blocks only on its own pipe, reads bounded byte chunks, immediately forwards bytes to the matching RunSentry output stream, and updates counters. The implementation never reads stdout to completion before stderr, never uses `readline()`, never waits for process exit before draining, and never uses `communicate()` to buffer full child output.

This avoids the classic deadlock where one pipe fills while the parent is waiting on the other pipe.

## Chunk Size

`READ_CHUNK_SIZE` is `65536` bytes.

The reader does not depend on newlines, complete text records, or printable output. Short reads, partial writes from the child, and output without trailing newlines are forwarded and counted as bytes.

## Byte Forwarding Behavior

stdout bytes are forwarded to `sys.stdout.buffer` when available. stderr bytes are forwarded to `sys.stderr.buffer` when available. If a stream has no `.buffer`, RunSentry falls back to an error-replacing text write for that unusual harness; normal terminal and subprocess pipe operation remains byte-oriented.

RunSentry does not prepend labels, timestamps, colors, or stream markers to child output.

## Binary Safety

The observation path does not decode child bytes for transport. Invalid UTF-8 and arbitrary binary bytes are counted and forwarded as bytes. Diagnostics about RunSentry itself are separate from child output and are intentionally minimal.

## Activity Fields

Each stream tracks:

- stream name
- total bytes observed
- total read/chunk events
- first activity monotonic timestamp
- last activity monotonic timestamp
- read error string, if any
- display/forwarding error string, if any
- EOF flag

No historical output content, line list, transcript, or unbounded buffer is retained.

## EOF and Shutdown Semantics

After the child exits, RunSentry joins both output reader threads before returning the child exit result. This lets residual tail output drain after process completion.

The join is bounded. If a descendant or inherited file descriptor keeps a pipe open after the root exits, RS-P0-004 does not wait forever. That case is treated as output-drain degradation, not process monitoring.

## Backpressure Limitations

RunSentry cannot make the user's terminal, pipe, or downstream consumer infinitely fast. If the final display destination is slower than the child, ordinary backpressure can still occur.

The RS-P0-004 guarantee is narrower: RunSentry continuously drains both child pipes concurrently and does not introduce avoidable deadlocks, unbounded memory growth, or stdout/stderr starvation in its own observation layer.

## Broken Output Sink Semantics

If forwarding to RunSentry stdout or stderr fails, the affected stream records a display error and disables further forwarding for that stream. The reader keeps draining child output where possible so the child is not blocked merely because display forwarding failed.

After child completion and pipe drain, RunSentry emits a best-effort observer diagnostic to `sys.__stderr__`. If that diagnostic stream is also unavailable, the diagnostic is silently dropped.

Display failure is distinct from child failure. RS-P0-004 does not terminate the child solely because display forwarding failed.

## Signal Behavior

RS-P0-004 keeps the RS-P0-003 foreground process-group approach. RunSentry does not create a new process group and does not manually forward SIGINT, avoiding duplicate Ctrl-C delivery under normal macOS/Linux terminal semantics.

If RunSentry observes `KeyboardInterrupt` while waiting or during output cleanup, it treats Ctrl-C as the controlling lifecycle fact, temporarily ignores repeated SIGINT during cleanup, gives the child a bounded wait, drains output where possible, restores the previous SIGINT handler for library callers, and returns `130`. It does not escalate to SIGKILL.

Local Python 3.9/macOS smoke validation showed that SIGINT delivery in the harness can be delayed until the child sleep completes, but the final RunSentry result was `130`. The test suite keeps this case bounded with a short child sleep and timeout.

## Tests Added

- stdout forwarding
- stderr forwarding
- stdout/stderr separation
- high-volume stdout
- high-volume stderr
- simultaneous high-volume stdout and stderr
- no-newline output
- partial/chunked output and activity counters
- invalid UTF-8/binary output
- silent child zero activity
- nonzero child exit with tail output drained
- Ctrl-C with output pipes
- broken forwarding sink continues draining
- activity object does not retain output content

## Validation Performed

- Repository root search: no RunSentry Git repository found; `/Users/zhangchao` contains the only RunSentry `pyproject.toml`.
- `python3 --version`: `Python 3.9.5`; below the RunSentry `>=3.10` contract.
- `python3 -m py_compile src/runsentry/__init__.py src/runsentry/__main__.py src/runsentry/cli.py src/runsentry/execution.py src/runsentry/output.py src/runsentry/version.py tests/test_cli.py tests/test_output.py`: passed under Python 3.9.5 as non-contract syntax smoke validation.
- `PYTHONPATH=src python3 -m runsentry run -- python3 -c "import sys; sys.stdout.write('OUT004'); sys.stderr.write('ERR004')"`: returned `0` and displayed both markers.
- `PYTHONPATH=src python3 -m runsentry run -- python3 -c "import os, sys; os.write(sys.stdout.fileno(), bytes([255, 254, 0, 65]))"`: returned `0` and forwarded binary bytes.
- `PYTHONPATH=src python3 -m runsentry run -- python3 -c "import sys; sys.stdout.write('TAIL'); raise SystemExit(7)"`: returned `7` and displayed tail output.
- Manual capture smoke confirmed stdout/stderr separation: stdout `OUT_ONLY`, stderr `ERR_ONLY`.
- Manual simultaneous high-volume smoke wrote `1310720` bytes to stdout and `1310720` bytes to stderr and completed with both byte streams exact.
- Manual activity smoke recorded 3 stdout bytes and activity timestamps.
- Manual broken-sink smoke drained `196608` bytes, recorded display failure, and reached EOF.
- Manual SIGINT smoke returned `130`, with local harness delay noted above.

## Validation Limitations

Local validation is not Python-contract-compliant because this iMac currently exposes only Python 3.9.5 and has no local pytest installation. `python3 -m pip install -e .`, `python3 -m pytest`, and installed `runsentry --help` remain unavailable for the same environment reason recorded in RS-P0-002 and RS-P0-003.

Contract-level validation is expected from GitHub Actions on Python 3.10, 3.11, and 3.12.

## Consciously Deferred Work

- psutil usage
- process-tree enumeration
- descendant lifecycle semantics
- CPU, RSS, RAM, swap, and disk sampling
- watched files/directories
- health states
- JSONL telemetry
- final run summary
- throughput
- job ETA
- disk ETA
- OOM risk
- notifications
- PTY
- shell mode
- automatic kill, recovery, or escalation
