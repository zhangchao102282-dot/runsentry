# RS-P0-005 Process Resource Record

## Objective

Implement the factual process/resource observation layer for a launched RunSentry root process. RS-P0-005 records process identity, root observability, observed descendants, CPU facts, RSS facts, system RAM facts, and swap facts.

This task does not interpret those facts. It does not implement health states, stall detection, OOM prediction, disk prediction, telemetry, ETA, notifications, automatic kill, or recovery.

## Process Identity Semantics

Process identity is represented as:

```text
(pid, create_time_epoch_s)
```

`pid` is always recorded. `create_time_epoch_s` is recorded when `psutil` can read it. PID alone is not treated as permanent identity. If a later process at the same PID has a different create time, the observation layer marks PID reuse instead of accepting it as the original process.

The root process is the direct child launched by RunSentry. `LaunchInfo` now carries the root PID, launch argv, monotonic launch time, root create time when available, and final return code.

## Descendant Registry Model

The observer keeps a bounded in-memory registry of descendants actually observed during the run. It does not claim knowledge of descendants that were never seen.

Each sample attempts to discover recursive descendants from the root when the root is still observable. Previously observed descendants are retained by identity and sampled individually, which gives later lifecycle code enough facts to reason about root exit with known live descendants.

The registry distinguishes currently observable descendants, previously observed descendants, disappeared descendants, inaccessible descendants with partial metrics, and possible PID reuse. No general process database or unbounded snapshot history is created.

## PID Reuse Protection

For any known process with a recorded create time, a later sample must match both PID and create time. A create-time mismatch marks PID reuse. PID reuse is exposed as factual observation-quality metadata and is not interpreted as job failure.

## Sampling Interval

Default resource sampling interval:

```text
1.0 seconds
```

The CLI exposes only the frozen `--interval` option, bounded to `1.0` through `60.0` seconds. No CPU, memory, or health threshold options were added.

Sampling runs in the execution/waiting thread using bounded `process.wait(timeout=sample_interval_s)` cycles. The existing stdout/stderr drain threads remain independent; output transport does not depend on resource sampling.

## CPU Semantics

CPU values use `psutil.Process.cpu_percent(interval=None)`.

The first sample for each process is a priming sample and reports `None`, because psutil's first non-blocking percentage is not meaningful interval data. Later samples report psutil's process CPU percent directly. Values are not normalized to 0-100 and may exceed 100 on multicore systems.

Tree CPU is the sum of successfully observed member CPU percentages. If no process has a meaningful CPU value for the sample, tree CPU is `None`.

## RSS and Tree RSS Semantics

Root RSS comes from `process.memory_info().rss` when available. Tree RSS is the sum of RSS values for successfully observed live root/descendant members.

Tree RSS is operational, not exact unique physical memory use. Shared pages may be counted multiple times. If any live known member lacks RSS due to access denial or race, `tree_rss_partial` is true and `observation_complete` is false.

## System RAM and Swap Fields

System RAM uses `psutil.virtual_memory()` and records total bytes, available bytes, used bytes, percent, and an unavailable flag.

Swap uses `psutil.swap_memory()` and records total bytes, used bytes, free bytes, percent, and an unavailable flag.

No thresholds, warnings, or OOM-risk interpretation are implemented.

## psutil Race and Error Handling

Expected process races degrade individual fields rather than fail the run.

Handled cases include `NoSuchProcess`, `AccessDenied`, `ZombieProcess`, PID create-time mismatch, and missing `psutil`. One inaccessible descendant does not invalidate the entire snapshot.

## Snapshot Storage

Production execution retains only `latest_resource_snapshot`. It does not accumulate an unbounded list of samples. Tests may explicitly collect snapshots when needed.

## Interaction With Output Threads

Output forwarding continues to use two independent pipe-drainer threads from RS-P0-004. Process/resource sampling occurs in the main wait loop. A slow or failing sample does not cause stdout to wait on stderr or stderr to wait on stdout.

## Tests Added

- root process observation and identity
- root RSS factual availability
- first/subsequent CPU sample semantics
- direct child discovery
- recursive child/grandchild discovery
- descendant registry retention after root exit
- short-lived child race does not crash
- process disappearance degrades gracefully
- tree RSS aggregation and completeness metadata
- system memory snapshot
- swap snapshot
- stdout/stderr coexistence while resource sampling runs
- nonzero child/root exit propagation remains intact
- bounded production snapshot retention

The process/resource tests are skipped when `psutil` is unavailable.

## Validation Performed

- `git status --short` before changes: clean.
- `git rev-parse --show-toplevel`: `/Users/zhangchao/ai-lab/runsentry`.
- Local Python: `Python 3.9.5`, below the project `>=3.10` contract.
- Local `psutil`: unavailable for Python 3.9.5.
- `python3 -m py_compile src/runsentry/__init__.py src/runsentry/__main__.py src/runsentry/cli.py src/runsentry/execution.py src/runsentry/output.py src/runsentry/observation.py src/runsentry/version.py tests/test_cli.py tests/test_output.py tests/test_observation.py`: passed under Python 3.9.5 as non-contract syntax smoke validation.
- `PYTHONPATH=src python3 -m runsentry --help`: passed.
- `PYTHONPATH=src python3 -m runsentry run --interval 1 -- python3 -c "print('OBS_SMOKE')"`: passed and printed `OBS_SMOKE`.
- `PYTHONPATH=src` direct execution fallback smoke: returned `0` and produced latest snapshot reason `psutil_unavailable`.
- `PYTHONPATH=src python3 -m runsentry run --interval 0.5 -- python3 -c "print('BAD_INTERVAL_SHOULD_NOT_RUN')"`: returned `2`; the child marker did not execute.
- RS-P0-004 dual-stream regression smoke: wrote `655360` bytes to stdout and `655360` bytes to stderr; both streams were exact and exit was `0`.
- RS-P0-004 broken-sink regression smoke: drained `196608` bytes, recorded display failure, and reached EOF.
- Exit propagation regression smoke: child output `TAIL` was forwarded and child exit `7` propagated as `7`.
- Ctrl-C regression smoke: returned `130` within the bounded harness.
- `python3 -m pytest`: failed locally because pytest is not installed.

## Validation Limitations

Local validation is not contract-compliant because this machine exposes only Python 3.9.5 and does not have psutil or pytest installed for that interpreter. The project Python requirement was not weakened. Full validation is expected from CI on Python 3.10, 3.11, and 3.12 after dependencies install.

## Consciously Deferred Interpretation Logic

- health state machine
- `STARTING`, `HEALTHY`, `QUIET`, `SUSPECTED_STALL`
- stall detection
- memory thresholds
- OOM risk prediction
- disk observation or prediction
- watched files/directories
- JSONL telemetry
- final run summary
- throughput
- job ETA
- disk ETA
- notifications
- PTY
- shell mode
- automatic workload kill
- automatic recovery
