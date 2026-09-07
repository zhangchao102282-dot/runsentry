# RS-P0-010B Sentinel Shadow Observation Record

## Objective

Run RunSentry in shadow-observation mode against a safe real-world task and compare
RunSentry telemetry/summary output against human expectations.

This was a dogfood/observation task. No RunSentry product functionality was changed, and
no Sentinel production behavior was modified.

## Environment

- Repository: `/Users/zhangchao/ai-lab/runsentry`
- Starting HEAD: `058c455 RS-P0-010A local dogfood smoke observation`
- Python: `3.12.14`
- Dogfood output root: `.runsentry/real-dogfood-010B/`

Generated dogfood artifacts were written under `.runsentry/`, which is ignored by Git.

## Candidate Commands Considered

### Sentinel candidates inspected

- `/Users/zhangchao/ai-lab/sentinel/sentinel_health_check.py`
- `/Users/zhangchao/ai-lab/sentinel/sentinel_status_report.py`
- `/Users/zhangchao/ai-lab/sentinel-local-ai/reports/local_sentinel_data_report_v1.py`
- `/Users/zhangchao/ai-lab/sentinel-local-ai/reports/market_db_freshness_inspector_v1.py`

### Candidate decisions

- `sentinel_health_check.py`: selected. It checks file and environment-variable presence,
  prints only OK/MISSING status, and does not write files, mutate databases, send
  notifications, place trades, or call external APIs.
- `sentinel_status_report.py`: rejected. It uses `sqlite3.connect("sentinel.db")` with a
  relative path and no explicit read-only URI, so safety depends on working directory and
  could create/open an unintended database.
- `local_sentinel_data_report_v1.py`: rejected. It writes report output under
  `sentinel-local-ai/reports/`.
- `market_db_freshness_inspector_v1.py`: rejected. It writes report/inventory outputs under
  `sentinel-local-ai/`.

Broader text scans were stopped after they ran longer than useful. The safe candidate set
above was sufficient for this task.

## Selected Dogfood Runs

Two runs were performed:

1. Sentinel shadow command: `sentinel_health_check.py`
2. Fallback real-world RunSentry repo command: synthetic pytest subset

The second run was used because the Sentinel health check is very quick; the pytest subset
provides a longer, more realistic local command with process/resource samples.

## Human Expectation Before Run

### sentinel_health_check_shadow

- Expected behavior: read-only local Sentinel environment/file presence check.
- Expected duration: very short.
- Expected CPU/activity style: low CPU, stdout active.
- Expected stdout/stderr: stdout status report; stderr empty.
- Expected watched-path behavior: no watched path configured.
- Expected final outcome: exit `0` if local files/env exist.
- `SUSPECTED_STALL` would be surprising.
- `QUIET` would be acceptable only if the task ran long enough after startup without
  activity.
- `FAILED` would be unexpected unless the script itself errored.

### runsentry_synthetic_subset_real_dogfood

- Expected behavior: run `pytest -q tests/test_synthetic_scenarios.py`.
- Expected duration: short-to-medium local development command.
- Expected CPU/activity style: intermittent CPU with mostly quiet pytest output.
- Expected stdout/stderr: concise pytest stdout; stderr empty.
- Expected watched-path behavior: no watched path configured.
- Expected final outcome: exit `0`.
- `SUSPECTED_STALL` would be surprising.
- `QUIET` would be acceptable because pytest is often silent while tests run.
- `FAILED` would be unexpected unless tests failed.

## Actual RunSentry Commands

### Sentinel health check

```text
.venv/bin/python -m runsentry run --name sentinel_health_check_shadow --output-dir .runsentry/real-dogfood-010B/sentinel_health -- /Users/zhangchao/ai-lab/sentinel/venv/bin/python /Users/zhangchao/ai-lab/sentinel/sentinel_health_check.py
```

### RunSentry synthetic pytest subset

```text
.venv/bin/python -m runsentry run --name runsentry_synthetic_subset_real_dogfood --output-dir .runsentry/real-dogfood-010B/pytest_synthetic -- .venv/bin/python -m pytest -q tests/test_synthetic_scenarios.py
```

## Actual Observations

| Run | Exit | Run ID | Run directory | Samples | Final health | Health transitions | stdout bytes | stderr bytes |
|---|---:|---|---|---:|---|---|---:|---:|
| Sentinel health check | `0` | `20260907T201938Z-5b408c240241` | `.runsentry/real-dogfood-010B/sentinel_health/runs/20260907T201938Z-5b408c240241` | `1` | `COMPLETE` | `STARTING -> COMPLETE` | `701` | `0` |
| Synthetic pytest subset | `0` | `20260907T201943Z-ab9990b098fc` | `.runsentry/real-dogfood-010B/pytest_synthetic/runs/20260907T201943Z-ab9990b098fc` | `11` | `COMPLETE` | `STARTING -> QUIET -> COMPLETE` | `99` | `0` |

Both runs produced:

- `telemetry.jsonl`
- `summary.json`
- `run_started`
- at least one `sample`
- `run_finished`

All inspected JSONL lines parsed successfully.

## Telemetry and Summary Review

### Sentinel health check

Key facts:

- exit code: `0`
- child return code: `0`
- final health: `COMPLETE`
- reason codes: `root_exit_zero`
- stdout bytes: `701`
- stderr bytes: `0`
- peak root RSS bytes: `110592`
- peak tree RSS bytes: `110592`
- max observable process count: `1`
- max observable descendants: `0`
- watched paths: none

Human review:

- The command, cwd, argv, exit code, health state, stdout/stderr counts, telemetry path,
  and process/resource facts were easy to locate in `summary.json`.
- The output confirmed the Sentinel health check printed file/env presence only and did
  not print token values.

### Synthetic pytest subset

Key facts:

- exit code: `0`
- child return code: `0`
- final health: `COMPLETE`
- reason codes: `root_exit_zero`
- stdout bytes: `99`
- stderr bytes: `0`
- sample count: `11`
- peak root RSS bytes: `28794880`
- peak tree RSS bytes: `28794880`
- max observable process count: `1`
- max observable descendants: `0`
- watched paths: none

Health transitions:

- `STARTING`
- `QUIET`
- `COMPLETE`

Human review:

- `QUIET` during pytest execution is acceptable because pytest was mostly silent after
  startup.
- No `SUSPECTED_STALL` appeared.
- Resource facts and sample count were useful enough to confirm RunSentry was observing
  the process while it ran.

## Forbidden Field Check

The following forbidden top-level fields were absent from inspected telemetry events and
summaries:

- `oom_risk`
- `disk_exhaustion_eta`
- `job_eta`
- `notification_status`
- `auto_kill_action`

No notification, dashboard, SaaS, AI judgment, automatic kill, recovery, ETA, OOM
prediction, or disk-exhaustion prediction behavior was implemented or observed.

## Human vs RunSentry Alignment

Classification:

```text
ALIGNED
```

Evaluation:

- RunSentry correctly identified completion for both commands.
- RunSentry avoided false `SUSPECTED_STALL`.
- stdout/stderr activity was captured as byte/chunk facts.
- resource facts were present and useful.
- no watched paths were configured, which matched the selected commands.
- `summary.json` was readable enough for a human inspection pass.
- telemetry volume was reasonable: sparse for the very short health check and useful for
  the longer pytest run.

## Issues Found

No correctness blocker was found.

Notes:

- The Sentinel command was safe but very short, so it provided limited health-state signal
  beyond lifecycle and artifact creation.
- The longer pytest command provided better sample-count and `QUIET` behavior signal.
- `summary.json` remains usable, but a future top-level `run_dir` field would make manual
  navigation slightly easier.

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

## Git Artifact Check

Dogfood artifacts were generated under:

```text
.runsentry/real-dogfood-010B/
```

`.runsentry/` is ignored by Git. No generated dogfood artifacts were tracked.

## Readiness for Public Alpha Preparation

Decision:

```text
READY_WITH_NOTES
```

Notes:

- Safe Sentinel shadow observation is aligned, but the Sentinel command was short.
- Before public alpha, run at least one longer non-mutating local development command with
  meaningful watched-path output to exercise `HEALTHY` and watched-path facts over a
  longer interval.
- Do not use RunSentry on live production Sentinel trading/update jobs until a separate
  safety review explicitly approves that use.
