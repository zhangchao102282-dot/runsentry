# RS-P0-008 Conservative Health State Machine Record

## Objective

Implement the P0 conservative health state machine using only facts already produced by
RS-P0-003 through RS-P0-007.

This task is the first RunSentry task that interprets observations, but interpretation is
strictly limited to deterministic P0 health states:

- `STARTING`
- `HEALTHY`
- `QUIET`
- `SUSPECTED_STALL`
- `FAILED`
- `COMPLETE`

No automatic intervention, prediction, notification, orchestration, dashboard, or AI-based
judgment was added.

## State Meanings

`STARTING` means the process has launched and remains within the initial observation
window.

`HEALTHY` means recent positive factual activity was observed.

`QUIET` means little observable activity exists, but evidence is insufficient to call the
run suspicious.

`SUSPECTED_STALL` means multiple independent observable signals show sustained inactivity
over the configured internal window.

`FAILED` means the wrapped command ended with a nonzero result other than the SIGINT
interruption convention.

`COMPLETE` means the wrapped command ended successfully according to the existing execution
exit semantics.

## Internal Timing Constants

P0 exposes no health tuning CLI options.

Default internal constants:

- `starting_window_s = 10.0`
- `quiet_window_s = 30.0`
- `suspected_stall_window_s = 120.0`
- `minimal_cpu_activity_threshold = 1.0`

Tests use explicit smaller `HealthConfig` values through the internal API rather than
adding CLI threshold sprawl.

## Transition Rules

The state machine records transition history only when the state changes.

Sample assessment order:

1. If elapsed time is inside `starting_window_s`, state is `STARTING`.
2. If recent positive activity exists after the starting window, state is `HEALTHY`.
3. If sustained multi-signal inactivity is defensible, state is `SUSPECTED_STALL`.
4. Otherwise state is `QUIET`.

Terminal assessment order:

1. Exit code `0` produces terminal `COMPLETE` with `root_exit_zero`.
2. Exit code `0` with known live descendants produces terminal `QUIET` with
   `root_exit_zero_known_descendants_alive`, not `COMPLETE`.
3. Exit code `130` produces terminal interrupted semantics with state `QUIET` and
   `interrupted_sigint`.
4. Other nonzero exit codes produce terminal `FAILED` with `root_exit_nonzero`.

Only `FAILED` and `COMPLETE` are ordinary terminal success/failure states. SIGINT is
terminal from the health-state-machine perspective, but it is not classified as ordinary
job failure.

## Positive Activity Evidence

Any of the following can make a non-starting sample `HEALTHY`:

- stdout or stderr total byte count increased;
- watched file/directory size changed;
- watched path mtime changed;
- observable CPU activity is at or above the internal threshold;
- observable process-tree counts changed.

RunSentry does not require all signals to be active. CPU-bound silent jobs, stdout-active
low-CPU jobs, and watched-file-writing low-CPU jobs can all be `HEALTHY`.

## Conservative Multi-Signal Stall Logic

`SUSPECTED_STALL` requires all of the following:

- elapsed inactivity duration at least `suspected_stall_window_s`;
- no stdout/stderr byte increase and output observation did not fail;
- CPU facts are available and below the minimal activity threshold;
- at least one watched path exists and is available;
- watched path facts show no size or mtime activity;
- no unknown/unavailable evidence reduces confidence.

No single inactivity signal can produce `SUSPECTED_STALL`.

Examples that are not enough by themselves:

- low CPU alone;
- no stdout/stderr alone;
- no watched-path growth alone;
- missing watch configuration;
- unavailable CPU;
- failed output observation;
- inaccessible watched paths.

## QUIET vs SUSPECTED_STALL

`QUIET` is the conservative fallback.

RunSentry emits `QUIET` when there is little activity but insufficient independent,
available evidence for `SUSPECTED_STALL`.

Examples:

- sleeping process with no output before the stall window;
- no watch paths configured;
- CPU unavailable;
- output observation unavailable;
- watched paths inaccessible;
- quiet-but-legitimate workloads.

Unknown evidence reduces suspicion rather than increasing it.

## Unavailable and Partial Evidence Behavior

Unavailable or partial facts add reason codes but do not become inactivity evidence.

Relevant reason codes include:

- `observation_partial`
- `output_observation_unavailable`
- `watched_path_unavailable`
- `cpu_unavailable`
- `insufficient_evidence_quiet`

Telemetry failure does not affect health evaluation of the running child. Health uses the
in-memory facts available from process, output, and watched-path observers.

## Recovery Behavior

`SUSPECTED_STALL` is recoverable.

If later positive activity appears, the state can return to `HEALTHY`, including from:

- output byte increases;
- watched path size/mtime activity;
- resumed CPU activity;
- process-tree activity.

`SUSPECTED_STALL` is not terminal.

## Telemetry Integration

Telemetry sample events now include:

- `health_state`
- `reason_codes`

`run_finished` events include:

- `health_state`
- `reason_codes`
- serialized final health object;
- health transition history.

No extra dashboard/display output was added.

## Summary Integration

`summary.json` now includes:

- `final_health_state`
- `final_reason_codes`
- `health_terminal`
- `health_transition_history`

Existing factual summary fields remain.

## Synthetic Scenario Alignment

Expected P0 alignment:

- `healthy_cpu.py`: `STARTING` then `HEALTHY` from `recent_cpu_activity`, final
  `COMPLETE` on exit `0`.
- `healthy_io.py`: `STARTING` then `HEALTHY` from output or watched-path activity,
  final `COMPLETE` on exit `0`.
- `quiet_but_healthy.py`: `STARTING` then normally `QUIET`; must not become
  `SUSPECTED_STALL` from silence alone.
- `hang_after_60s.py`: may become `SUSPECTED_STALL` only after the internal sustained
  multi-signal window and only if output, CPU, and watched-path facts are all available
  and inactive.
- `crash_after_60s.py`: final `FAILED` from nonzero root exit.
- `child_process_crash.py`: child disappearance alone is not overall `FAILED`; root exit
  remains the primary final authority for P0 execution semantics.
- `disk_writer.py`: watched-path growth should produce `HEALTHY`; no disk exhaustion
  prediction is emitted.

Full dogfood remains deferred.

## Tests

Added `tests/test_health.py` covering:

- initial `STARTING`;
- stdout activity to `HEALTHY`;
- stderr activity to `HEALTHY`;
- watched file growth to `HEALTHY`;
- CPU-bound silent task to `HEALTHY`;
- quiet sleeping task to `QUIET`;
- quiet-but-healthy silence not becoming `SUSPECTED_STALL`;
- no watch path not counting as stall evidence;
- output observation unavailable not counting as silence;
- watched path unavailable not counting as no-growth;
- CPU unavailable not counting as low CPU;
- sustained multi-signal inactivity becoming `SUSPECTED_STALL`;
- recovery from `SUSPECTED_STALL` via output activity;
- recovery from `SUSPECTED_STALL` via watched-path growth;
- exit `0` to `COMPLETE`;
- nonzero exit to `FAILED`;
- SIGINT terminal interrupted semantics;
- telemetry sample health fields;
- summary final health and transition history;
- high-volume stdout/stderr regression;
- SIGINT summary regression.

## Validation Result

Local validation environment:

- Python: 3.12.14

Commands run:

```text
.venv/bin/python -m py_compile src/runsentry/*.py tests/test_health.py
.venv/bin/python -m pytest -q tests/test_health.py
.venv/bin/python -m pytest -q
```

Results:

- health suite: `21 passed`
- full suite: `95 passed, 3 skipped`
- focused health/telemetry/output/process/watch regression set: `27 passed`

The three skips are existing macOS psutil descendant-enumeration skips, not health-state
failures.

## Consciously Deferred Prediction/Notification Logic

Deferred:

- OOM prediction;
- disk exhaustion prediction;
- ETA;
- throughput judgment;
- notifications;
- dashboard or web UI;
- remote monitoring;
- AI/LLM judgment;
- automatic kill;
- automatic recovery;
- workflow orchestration.
