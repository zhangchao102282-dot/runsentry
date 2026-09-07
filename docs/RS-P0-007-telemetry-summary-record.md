# RS-P0-007 JSONL Telemetry and Summary Fact Persistence Record

## Objective

Persist factual RunSentry observations from RS-P0-003 through RS-P0-006 to local disk.

This task persists launch facts, command argv, process/resource snapshots,
stdout/stderr activity counters, watched-path facts, disk facts, and a final factual
summary. It does not add health judgment, stall detection, OOM risk, disk exhaustion
prediction, ETA, throughput judgment, notifications, recovery, or automatic kill logic.

## Output Directory Structure

Default output is local to the current working directory:

```text
.runsentry/
  runs/
    <run_id>/
      telemetry.jsonl
      summary.json
```

`.runsentry/` is git-ignored because it is local runtime output.

The CLI also supports one minimal override:

```text
runsentry run --output-dir PATH -- COMMAND [ARG ...]
```

When `--output-dir` is supplied, RunSentry writes:

```text
PATH/
  runs/
    <run_id>/
      telemetry.jsonl
      summary.json
```

No dashboard, database, index, upload, or service files are created.

## Run ID Semantics

Run IDs are generated once at execution start and remain stable for the run.

Format:

```text
YYYYMMDDTHHMMSSZ-<12_hex_uuid_chars>
```

Example:

```text
20260907T162040Z-8058fee99384
```

This is filesystem-safe and unique enough for local concurrent runs with high probability.
It uses local process generation only; no external services are involved.

## JSONL Schema

Schema version:

```text
rs-p0-telemetry-v1
```

Every telemetry line is one JSON object with common fields:

- `schema_version`
- `run_id`
- `event_type`
- `timestamp_epoch_s`
- `elapsed_s`

RunSentry writes each JSON object as a single line and does not retain all events in
memory.

## Event Types

Implemented event types:

- `run_started`
- `sample`
- `run_finished`

No health-state transition events exist in RS-P0-007.

## `run_started` Contents

The `run_started` event contains:

- run ID
- optional run name
- command argv
- root PID
- root create time where available
- start timestamp
- cwd
- configured watched paths
- sample interval
- schema version and event type

It contains factual launch configuration only.

## `sample` Contents

Sample events are written:

- once after launch and initial observation;
- periodically on the existing sample interval during execution.

Each sample includes:

- process/resource facts from the current `ResourceSnapshot`;
- stdout/stderr byte and chunk counters;
- stdout/stderr first/last activity timestamps;
- stdout/stderr EOF and error flags;
- watched-path observations;
- disk usage facts attached to watched paths.

The event stores output counters only, never stdout/stderr content.

## `run_finished` Contents

At run end, RunSentry writes one `run_finished` event containing:

- final exit code
- child/root return code where available
- end timestamp
- duration
- output-drained flag
- final stdout/stderr activity facts
- final process snapshot
- final watched-path observations
- factual aggregate peaks:
  - peak root RSS bytes
  - peak tree RSS bytes
  - max observable process count
  - max observable descendant count

No health, stall, OOM, disk exhaustion, ETA, or throughput judgment fields are emitted.

## `summary.json` Contents

At run end, RunSentry writes a single JSON summary containing:

- `schema_version`
- `run_id`
- `name`
- `argv`
- `cwd`
- `start_timestamp_epoch_s`
- `end_timestamp_epoch_s`
- `duration_s`
- `exit_code`
- `child_returncode`
- `sample_count`
- `output_drained`
- stdout/stderr byte, chunk, first/last, EOF, and error facts
- peak root RSS bytes
- peak tree RSS bytes
- max observable process count
- max observable descendant count
- final watched-path observations
- telemetry file path
- consciously absent fields:
  - `health_state`
  - `stall_status`
  - `oom_risk`
  - `disk_exhaustion_eta`
  - `job_eta`

Unknown values are serialized as JSON `null`.

## Serialization Choices

Serialization is explicit. RunSentry does not rely on blanket `dataclasses.asdict()`.

Reasons:

- avoid internal fields;
- keep paths as strings;
- keep errors as booleans or concise strings;
- keep process identities as plain JSON objects;
- prevent stdout/stderr content from entering telemetry through stream activity objects.

Command argv is intentionally persisted as launch fact. If a user embeds sensitive text
inside command arguments, that text is part of the factual command line and will appear in
telemetry.

## Flushing and Durability Policy

Durability is simple and local:

- one JSON object per line;
- `run_started` is flushed;
- `run_finished` is flushed;
- sample events are written incrementally and not retained in memory;
- `summary.json` is written at run end and flushed.

This is not a database and does not provide transactional guarantees. A crash can leave a
partial final line, but previous completed JSONL lines remain independently parseable.

## Telemetry Failure Behavior

Telemetry initialization happens before child launch. If RunSentry cannot create the
output directory or open `telemetry.jsonl`, the child is not launched and RunSentry exits
with an internal error through the existing `LaunchError` path.

After launch:

- telemetry write/serialization/flush failures are recorded internally;
- a concise diagnostic is written to stderr when safe;
- further telemetry writes are disabled;
- the child workload is not killed;
- the child exit code remains authoritative where possible.

Summary write failure is reported to stderr where safe and does not alter the child exit
code.

## Sampling Integration

Telemetry sampling uses the existing execution wait loop and existing sample interval.
There is no independent telemetry thread or uncontrolled sampling loop.

Output pipe draining remains in the existing stdout/stderr drainer threads. Telemetry
writing occurs from the main wait/sampling path and stores only counters/facts.

The telemetry writer retains only:

- sample count;
- peak root RSS;
- peak tree RSS;
- max observable process count;
- max observable descendant count;
- current run paths and error flags.

It does not retain an unbounded event list.

## Tests

Added `tests/test_telemetry.py` covering:

- default `.runsentry/runs/<run_id>/` directory creation;
- `telemetry.jsonl` creation;
- `summary.json` creation;
- JSONL validity;
- common event fields;
- `run_started` launch/config facts;
- sample event creation;
- `run_finished` exit/duration/output/peak facts;
- summary fields;
- output content exclusion with output byte counts retained;
- watched-path telemetry;
- no-watch telemetry;
- nonzero exit telemetry;
- SIGINT telemetry;
- command-not-found behavior;
- output directory creation failure before child launch;
- during-run telemetry write failure not killing child;
- summary write failure not changing child exit code;
- high-volume stdout/stderr regression;
- bounded telemetry writer memory shape;
- run ID uniqueness;
- post-boundary `--watch` argv preservation;
- `.runsentry/` gitignore coverage.

## Validation Result

Local validation environment:

- Python: 3.12.14

Commands run:

```text
.venv/bin/python -m py_compile src/runsentry/*.py
.venv/bin/python -m pytest -q tests/test_telemetry.py
.venv/bin/python -m pytest -q
```

Results:

- telemetry suite: `20 passed`
- full suite: `74 passed, 3 skipped`

The three skips are existing macOS psutil descendant-enumeration skips from RS-P0-005A
validation behavior, not telemetry failures.

## Consciously Deferred Health/Prediction Logic

Deferred:

- health state machine;
- STARTING/HEALTHY/QUIET/SUSPECTED_STALL events;
- stall detection;
- OOM risk prediction;
- disk exhaustion prediction;
- ETA;
- throughput judgment;
- notifications;
- dashboards;
- databases;
- remote upload;
- automatic kill/recovery.
