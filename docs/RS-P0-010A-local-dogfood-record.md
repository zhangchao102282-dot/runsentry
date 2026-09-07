# RS-P0-010A Local Dogfood Smoke Observation Record

## Objective

Run RunSentry against its own synthetic workloads as a local dogfood smoke test.

This was an observation-only task. No RunSentry product functionality was added or
changed.

## Environment

- Repository: `/Users/zhangchao/ai-lab/runsentry`
- Starting HEAD: `5c32ffb RS-P0-009 synthetic integration scenarios`
- Python: `3.12.14`
- Dogfood artifact root: `/private/tmp/runsentry-dogfood-KDQz8H`

The dogfood root is outside the repository, so generated run artifacts are not tracked.

## Commands Run

### healthy_io.py

```text
.venv/bin/python -m runsentry run --output-dir /private/tmp/runsentry-dogfood-KDQz8H/healthy_io/rs --watch /private/tmp/runsentry-dogfood-KDQz8H/healthy_io/out.log -- .venv/bin/python tests/synthetic/healthy_io.py --output-file /private/tmp/runsentry-dogfood-KDQz8H/healthy_io/out.log --iterations 5 --delay-seconds 0.1
```

### quiet_but_healthy.py

```text
.venv/bin/python -m runsentry run --output-dir /private/tmp/runsentry-dogfood-KDQz8H/quiet/rs -- .venv/bin/python tests/synthetic/quiet_but_healthy.py --duration-seconds 0.6
```

### crash_after_60s.py

```text
.venv/bin/python -m runsentry run --output-dir /private/tmp/runsentry-dogfood-KDQz8H/crash/rs -- .venv/bin/python tests/synthetic/crash_after_60s.py --after-seconds 0.2 --exit-code 7
```

### hang_after_60s.py

```text
.venv/bin/python -m runsentry run --output-dir /private/tmp/runsentry-dogfood-KDQz8H/hang/rs --watch /private/tmp/runsentry-dogfood-KDQz8H/hang/watch.txt -- .venv/bin/python tests/synthetic/hang_after_60s.py --after-seconds 0.2 --hang-seconds 0.8 --watch-file /private/tmp/runsentry-dogfood-KDQz8H/hang/watch.txt
```

### disk_writer.py

```text
.venv/bin/python -m runsentry run --output-dir /private/tmp/runsentry-dogfood-KDQz8H/disk/rs --watch /private/tmp/runsentry-dogfood-KDQz8H/disk/outdir -- .venv/bin/python tests/synthetic/disk_writer.py --output-dir /private/tmp/runsentry-dogfood-KDQz8H/disk/outdir --files 4 --bytes-per-file 128 --delay-seconds 0.05
```

## Run Results

| Scenario | Exit code | Run ID | Final health | Telemetry lines | Event types | stdout bytes | stderr bytes |
|---|---:|---|---|---:|---|---:|---:|
| `healthy_io.py` | `0` | `20260907T193308Z-acf8d5f3385b` | `COMPLETE` | `4` | `run_started`, `sample`, `run_finished` | `65` | `0` |
| `quiet_but_healthy.py` | `0` | `20260907T193308Z-966fe4850461` | `COMPLETE` | `3` | `run_started`, `sample`, `run_finished` | `0` | `0` |
| `crash_after_60s.py` | `7` | `20260907T193308Z-e69e80070ac2` | `FAILED` | `3` | `run_started`, `sample`, `run_finished` | `23` | `25` |
| `hang_after_60s.py` | `0` | `20260907T193308Z-b6d7e00c4389` | `COMPLETE` | `4` | `run_started`, `sample`, `run_finished` | `59` | `0` |
| `disk_writer.py` | `0` | `20260907T193315Z-73b44b6fc94c` | `COMPLETE` | `3` | `run_started`, `sample`, `run_finished` | `124` | `0` |

## Run Directories

- `healthy_io.py`: `/private/tmp/runsentry-dogfood-KDQz8H/healthy_io/rs/runs/20260907T193308Z-acf8d5f3385b`
- `quiet_but_healthy.py`: `/private/tmp/runsentry-dogfood-KDQz8H/quiet/rs/runs/20260907T193308Z-966fe4850461`
- `crash_after_60s.py`: `/private/tmp/runsentry-dogfood-KDQz8H/crash/rs/runs/20260907T193308Z-e69e80070ac2`
- `hang_after_60s.py`: `/private/tmp/runsentry-dogfood-KDQz8H/hang/rs/runs/20260907T193308Z-b6d7e00c4389`
- `disk_writer.py`: `/private/tmp/runsentry-dogfood-KDQz8H/disk/rs/runs/20260907T193315Z-73b44b6fc94c`

Each run directory contained:

- `telemetry.jsonl`
- `summary.json`

All inspected JSONL lines parsed successfully.

## Health-State Observations

Observed health states:

- `healthy_io.py`: `STARTING`, `COMPLETE`
- `quiet_but_healthy.py`: `STARTING`, `COMPLETE`
- `crash_after_60s.py`: `STARTING`, `FAILED`
- `hang_after_60s.py`: `STARTING`, `COMPLETE`
- `disk_writer.py`: `STARTING`, `COMPLETE`

No dogfood run produced `SUSPECTED_STALL`.

This is expected for short smoke runs because production `starting_window_s` remains
conservative at 10 seconds. The `hang_after_60s.py` smoke run validates that RunSentry
does not immediately mark a bounded quiet period as suspicious. Full shortened-window
stall behavior remains covered by the synthetic health-state-machine tests.

## Watched-Path Observations

### healthy_io.py

Watched path:

```text
/private/tmp/runsentry-dogfood-KDQz8H/healthy_io/out.log
```

Observed facts:

- initial sample: `missing`
- later sample: `file`, `changed_since_previous_sample = true`
- final size: `65` bytes
- disk usage facts present

### hang_after_60s.py

Watched path:

```text
/private/tmp/runsentry-dogfood-KDQz8H/hang/watch.txt
```

Observed facts:

- initial sample: `missing`
- later sample: `file`, `changed_since_previous_sample = true`
- final size: `7` bytes
- disk usage facts present

### disk_writer.py

Watched path:

```text
/private/tmp/runsentry-dogfood-KDQz8H/disk/outdir
```

Observed facts:

- initial sample: `missing`
- final sample: `directory`, `changed_since_previous_sample = true`
- aggregate size: `512` bytes
- file count: `4`
- disk usage facts present

Creation transitions correctly show activity. Numeric `size_delta_bytes` is `null` when
the previous sample had no measurable size, which is defensible but less convenient for a
human reader.

## Forbidden-Field Checks

The following forbidden top-level fields were absent from inspected telemetry events and
summaries:

- `oom_risk`
- `disk_exhaustion_eta`
- `job_eta`
- `notification_status`
- `auto_kill_action`

No notification, dashboard, SaaS, AI judgment, automatic kill, recovery, ETA, OOM
prediction, or disk-exhaustion prediction behavior was observed.

## Usability Review

### Can a user tell what command ran?

Yes. `summary.json` includes `argv`, `cwd`, `run_id`, and the telemetry path.

### Can a user tell whether it completed or failed?

Yes. `exit_code`, `child_returncode`, `final_health_state`, and `final_reason_codes` are
present. The crash scenario clearly shows exit code `7` and final health `FAILED`.

### Can a user tell whether it was quiet or active?

Partially. stdout/stderr byte counts and watched-path facts are clear. For short smoke
runs, health transitions mostly show `STARTING -> COMPLETE` due the conservative
production starting window, so short summaries do not demonstrate intermediate activity
classification well.

### Can a user see stdout/stderr activity counts?

Yes. `summary.json` contains stdout/stderr byte and chunk counters, first/last activity
timestamps, EOF flags, and error flags.

### Can a user see watched path growth?

Yes. Watched paths show current size, kind, `changed_since_previous_sample`, file count
for directories, and disk usage facts. Creation-from-missing activity is visible, but
numeric size delta is `null` when the previous path was missing.

### Can a user find the telemetry path?

Yes. `summary.json` includes `telemetry_file_path`.

### Are field names understandable?

Mostly yes. The summary is factual and inspectable. Some field names are implementation
oriented, such as `current_alive_known_process_count` inside telemetry process snapshots,
but they are accurate.

### Obvious missing facts already available internally

Potential future usability improvements:

- include `run_dir` in `summary.json` alongside `telemetry_file_path`;
- include a compact top-level `event_types` or `sample_count_by_type`;
- include a top-level watched-path summary such as total watched paths and unavailable
  watched paths;
- consider representing missing-to-file/directory creation size as a separate
  `created_since_previous_sample` fact rather than relying only on
  `changed_since_previous_sample`.

None of these block Sentinel dogfood.

### Misleading fields

No blocking misleading field was found. The main caveat is that short runs can look like
`STARTING -> COMPLETE` even when they performed useful work. This follows the conservative
health contract and should be acceptable for P0, but users should know short smoke runs
may not demonstrate intermediate `HEALTHY`.

## Problems Found

No correctness blocker was found.

Notes:

- `size_delta_bytes` is `null` for creation transitions from missing to existing because
  there is no previous measurable size.
- short runs usually complete inside `starting_window_s`, so health history is concise but
  not very expressive.

## Fixes Made

No code fixes were made.

Only this documentation record was created.

## Post-Dogfood Validation

Command:

```text
.venv/bin/python -m pytest -q
```

Result:

```text
106 passed, 3 skipped
```

The three skips are existing macOS psutil descendant-enumeration skips.

## Repository Artifact Check

Dogfood artifacts were written under `/private/tmp/runsentry-dogfood-KDQz8H`, outside the
repository.

Repository status after dogfood and before this record:

- no tracked or untracked dogfood artifacts in the repository

`.runsentry/` remains ignored for default local runs.

## Sentinel Dogfood Readiness

Decision:

```text
READY_WITH_NOTES
```

RunSentry is ready for a Sentinel shadow-observation smoke pass, with notes:

- do not expect short jobs to show intermediate `HEALTHY` if they complete within the
  starting window;
- inspect watched-path creation transitions via `changed_since_previous_sample`, current
  size, and kind rather than relying on `size_delta_bytes` for initially missing paths;
- treat summary usability improvements as non-blocking follow-up work.
