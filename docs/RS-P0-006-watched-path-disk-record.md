# RS-P0-006 Watched Path and Disk Fact Observation Record

## Objective

Implement the watched-path and disk fact observation layer for RunSentry P0.

This task adds factual observation only. It does not add health states, stall detection,
disk exhaustion prediction, OOM prediction, telemetry, ETA, notifications, recovery, or
automatic workload termination.

## Watched Path Model

RunSentry now accepts zero or more `--watch PATH` options before the explicit command
boundary:

```text
runsentry run --watch out.log --watch output_dir -- python3 job.py
```

Rules:

- `--watch` before `--` is a RunSentry option.
- everything after `--` remains child argv unchanged.
- `--watch` after `--` belongs to the child.
- missing watched paths are allowed and may appear later.
- no watched path remains valid.

Each watched path produces a `WatchedPathObservation` fact object with:

- original path string
- absolute path string
- existence flag
- kind: `file`, `directory`, `other`, `missing`, or `inaccessible`
- file size for regular files
- aggregate recursive size for directories
- recursive file count for directories
- latest observed mtime
- device/inode identity where available
- changed-since-previous-sample flag
- size delta where meaningful
- mtime-change flag where meaningful
- replacement flag where device/inode comparison is defensible
- partial observation flag
- unavailable reason where applicable
- disk usage snapshot where available

## File Observation Semantics

Regular files are observed with standard `pathlib.Path.stat()` behavior. For existing
files, RunSentry records:

- `size_bytes`
- `latest_mtime_epoch_s`
- `device_id`
- `inode`

Growth is represented as `size_delta_bytes > 0` between consecutive samples. Shrinkage is
represented as a negative delta. No judgment is attached to either fact.

## Directory Observation Semantics

Directories are scanned recursively by polling with `os.scandir()`.

RunSentry records:

- aggregate size of regular files under the directory
- recursive regular file count
- latest mtime seen from directory entries
- directory device/inode identity
- whether the scan was partial

The scanner does not follow symlinked directories, avoiding symlink loops. It does not
maintain a file index and does not use filesystem event APIs such as inotify, FSEvents, or
watchdog.

Directory scanning is intentionally simple. Large trees may make a sample slower. Output
pipe draining remains independent in its own threads, but the main execution sampling loop
can spend time in a directory scan.

## Missing, Deleted, and Replaced Semantics

Missing paths produce:

- `exists = False`
- `kind = "missing"`
- no size/mtime/identity facts
- disk facts from the nearest existing ancestor when available

Deletion is observed as a transition from an existing kind to `missing`.

Replacement is detected when both previous and current samples expose device/inode identity
and the identity changes. If identity is unavailable on a platform or path type,
`replaced_since_previous_sample` is `None`.

## Inode/Device Limitations

Device and inode values come from `stat()` fields available on macOS and Linux. They are
useful for detecting replacement, but RunSentry treats replacement detection as best-effort:

- if both samples have identity and identity differs, replacement is recorded as `True`;
- if either identity is unavailable, replacement is `None`;
- no higher-level failure or health judgment is inferred.

## Disk Usage Semantics

Each watched path gets a `DiskUsageSnapshot` when a relevant filesystem can be determined.

The snapshot contains:

- filesystem path used for `shutil.disk_usage()`
- total bytes
- used bytes
- free bytes
- unavailable reason when disk usage could not be sampled

For an existing watched path, the path itself is used. For a missing watched path, RunSentry
walks upward to the nearest existing ancestor and samples disk usage there.

No disk exhaustion estimate, low-disk warning, threshold, or ETA is produced in RS-P0-006.

## Nearest Existing Ancestor Behavior

For deeply missing paths, RunSentry checks parents until it finds an existing path. If no
existing ancestor can be determined, disk facts are unavailable with
`no_existing_ancestor`.

If checking an ancestor raises `PermissionError`, that ancestor is used for disk sampling
and any disk usage failure is recorded as a factual unavailable reason.

## Sampling Integration

Watched-path sampling is integrated with the existing execution loop:

- one initial sample after child launch;
- periodic samples aligned with the existing resource sampling interval;
- one final sample before producing `ExecutionResult`.

`ExecutionResult` now exposes `latest_watched_paths`, a bounded tuple containing only the
latest observation for each configured watched path.

The `PathObserver` retains only:

- latest observation tuple;
- previous observation per original watched path, needed for deltas.

It does not accumulate an unbounded sample history.

## Tests

Added `tests/test_watch.py` covering:

- no watch paths allowed;
- `--watch` before `--` parsed as RunSentry option;
- `--watch` after `--` preserved as child argv;
- existing regular file size/mtime/disk facts;
- regular file growth and positive delta;
- file growth during execution;
- missing path appearing later;
- watched file deletion;
- watched file replacement via inode/device where available;
- recursive directory aggregate size and file count;
- directory growth;
- directory race handling;
- inaccessible path behavior via monkeypatch;
- disk usage for existing-parent and deeply missing paths;
- multiple watched paths;
- output/process regression with watching enabled;
- SIGINT regression with watching enabled;
- bounded watcher history.

## Validation Result

Local validation environment:

- Python: 3.12.14

Commands run:

```text
.venv/bin/python -m py_compile src/runsentry/*.py tests/test_watch.py
.venv/bin/python -m pytest -q tests/test_watch.py
.venv/bin/python -m pytest -q
```

Results:

- watch suite: `19 passed`
- full suite: `54 passed, 3 skipped`

The three skips are existing macOS psutil descendant-enumeration skips from the process
observation layer, not watched-path/disk failures.

## Consciously Deferred Work

Deferred to later P0 tasks:

- health state machine;
- stall detection;
- disk exhaustion prediction;
- throughput interpretation;
- job ETA;
- JSONL telemetry;
- final summaries;
- notifications;
- filesystem event watching;
- directory scan optimization/indexing;
- thresholds or warning generation.
