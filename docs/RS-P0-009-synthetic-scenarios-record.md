# RS-P0-009 Synthetic Integration Scenarios Record

## Objective

Create and run a safe P0 synthetic integration scenario suite for RunSentry.

The suite validates end-to-end behavior for controlled workloads that exercise:

- command execution;
- stdout/stderr observation;
- process/resource facts;
- watched-path facts;
- disk facts;
- JSONL telemetry;
- `summary.json`;
- conservative health states;
- terminal exit semantics.

No product features were added for notifications, dashboards, SaaS, AI judgment,
automatic kill, recovery, ETA, OOM prediction, or disk exhaustion prediction.

## Scenario Scripts Created

Synthetic scripts live under:

```text
tests/synthetic/
```

Scripts:

- `healthy_cpu.py`
- `healthy_io.py`
- `quiet_but_healthy.py`
- `memory_growth.py`
- `hang_after_60s.py`
- `crash_after_60s.py`
- `child_process_crash.py`
- `disk_writer.py`

The scripts use argument-controlled durations and sizes so test runs remain safe and
CI-friendly. The `after_60s` names are preserved for product alignment, but tests pass
short scaled-down durations.

## Execution Method

Most scenarios are exercised through the real CLI:

```text
python -m runsentry run --output-dir TMPDIR/runsentry-output [--watch PATH ...] -- python tests/synthetic/<scenario>.py ...
```

Tests then inspect:

- process exit code;
- `telemetry.jsonl`;
- `summary.json`;
- event types;
- health states;
- reason codes where relevant;
- watched-path facts;
- stdout/stderr byte counts;
- absence of forbidden prediction/intervention fields at top level.

Long-window stall behavior is validated directly through the internal
`HealthStateMachine` using a small test-only `HealthConfig`. No CLI health tuning option
was added.

## Scenario Acceptance Matrix

| Scenario | Workload behavior | Expected exit | Expected health | MUST NOT occur | Telemetry/summary expectations | Failure criteria |
|---|---:|---:|---|---|---|---|
| `healthy_cpu.py` | bounded CPU loop with stdout | `0` | short CLI run: `STARTING` then final `COMPLETE`; direct health tests cover CPU activity to `HEALTHY` | `SUSPECTED_STALL` | stdout byte count, run events, final summary | nonzero exit, missing telemetry/summary, suspected stall |
| `healthy_io.py` | repeated stdout and watched file writes | `0` | final `COMPLETE`; health-machine coverage for output/watch activity to `HEALTHY` | `SUSPECTED_STALL` | watched file size/disk facts, stdout bytes | no watched growth facts, missing disk facts, suspected stall |
| `quiet_but_healthy.py` | bounded quiet sleep | `0` | final `COMPLETE`; silence alone must not stall | `SUSPECTED_STALL` | zero stdout/stderr bytes are factual, not failure | suspected stall or output silence treated as failure |
| `memory_growth.py` | safe small incremental allocation | `0` | final `COMPLETE`; may be `STARTING`/`QUIET`/`HEALTHY` during samples depending on facts | OOM claim, OOM warning, failure due to safe growth | RSS peak key present where observable | OOM prediction field or nonzero exit |
| `hang_after_60s.py` | initial activity, then bounded inactivity | `0` for short CLI run | final `COMPLETE`; direct health-machine test shows `SUSPECTED_STALL` only after shortened multi-signal window | immediate `SUSPECTED_STALL` | watched file facts and run events | stall before configured window or missing telemetry |
| `crash_after_60s.py` | brief run then nonzero exit | configured nonzero, test uses `7` | final `FAILED` | fake stall requirement | stderr byte count, failed summary, exit propagation | wrong exit code or missing final telemetry |
| `child_process_crash.py` | child exits nonzero, root exits `0` | `0` | final `COMPLETE` when root succeeds and no known live descendants remain | final `FAILED` solely due child crash | child root return semantics preserved; no invented descendant exit code | child crash classified as root failure |
| `disk_writer.py` | writes bounded files into watched directory | `0` | final `COMPLETE`; watch activity supports health in health-machine tests | disk ETA, low-disk warning, exhaustion prediction | directory aggregate size, file count, disk facts | missing directory facts or forbidden prediction fields |

## Health-State Expectations

Production health windows remain conservative. Short CLI synthetic runs normally finish
inside `starting_window_s`, so tests do not require exact intermediate `HEALTHY` states
from CLI telemetry.

The following qualitative expectations are asserted:

- successful scenarios end with `COMPLETE`;
- crash scenario ends with `FAILED`;
- quiet scenarios do not reach `SUSPECTED_STALL`;
- child-process crash alone does not make a successful root command `FAILED`;
- direct health-machine test confirms `hang_after_60s` style inactivity reaches
  `SUSPECTED_STALL` only after the configured multi-signal window.

## Telemetry and Summary Assertions

For each CLI scenario, tests assert:

- `run_started` exists;
- at least one `sample` exists;
- `run_finished` exists;
- every JSONL line is valid JSON;
- all events share the summary run ID;
- common event fields exist;
- `final_health_state` exists;
- `health_transition_history` exists;
- relevant stdout/stderr byte counts are present;
- watched-path facts exist where `--watch` is used.

Forbidden prediction/intervention fields are absent as top-level telemetry/summary facts:

- `oom_risk`
- `disk_exhaustion_eta`
- `job_eta`
- `notification_status`
- `auto_kill_action`

The summary may still list some names in `consciously_absent_fields` as a documented
absence marker from RS-P0-007.

## Output and Watch Path Regression Coverage

The synthetic suite checks:

- stdout byte forwarding via `healthy_cpu.py`, `healthy_io.py`, and other scripts;
- stderr byte draining via `crash_after_60s.py`;
- watched file growth via `healthy_io.py`;
- watched directory aggregate growth via `disk_writer.py`;
- disk usage facts on watched paths;
- no stdout content persisted in telemetry/summary.

## Process Regression Coverage

The synthetic suite checks:

- root process lifecycle through every CLI scenario;
- descendant process creation/disappearance through `child_process_crash.py`;
- root exit semantics remain authoritative;
- descendant exit code is not invented when RunSentry is not the descendant parent.

## Validation Result

Local validation environment:

- Python: 3.12.14

Commands run:

```text
.venv/bin/python -m py_compile src/runsentry/*.py tests/synthetic/*.py tests/test_synthetic_scenarios.py
.venv/bin/python -m pytest -q tests/test_synthetic_scenarios.py
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/test_synthetic_scenarios.py tests/test_output.py::test_simultaneous_high_volume_stdout_and_stderr_complete_without_deadlock tests/test_observation.py::test_system_memory_and_swap_snapshots_are_factual tests/test_watch.py::test_watched_regular_file_growth_records_positive_delta tests/test_telemetry.py::test_summary_contains_expected_factual_fields tests/test_health.py::test_sustained_multi_signal_inactivity_can_become_suspected_stall
```

Observed results:

- `10 passed`
- `106 passed, 3 skipped`
- `15 passed`

The three skips are existing macOS psutil descendant-enumeration skips, not synthetic
scenario failures.

## Small Fixes Made

No RunSentry product behavior fixes were needed for RS-P0-009.

The only new code is validation infrastructure: synthetic workloads, integration tests,
and this record.

## Consciously Deferred Dogfood

Deferred:

- Sentinel shadow-observation dogfood;
- long-runtime `hang_after_60s.py` validation with production timing windows;
- public alpha acceptance runs on additional machines;
- performance profiling of large watched directories;
- any notification, recovery, dashboard, ETA, OOM, or disk-exhaustion work.
