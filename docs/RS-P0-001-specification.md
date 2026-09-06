# RunSentry P0 Specification and Architecture

**Task:** RS-P0-001 / RS-P0-001A  
**Status:** Decision-frozen, implementation-ready P0 design  
**Target:** Python 3.10+, macOS and Linux, `psutil` plus standard library

RunSentry P0 is a local observer around one directly executed command. It is not a scheduler, workflow engine, recovery service, dashboard, remote service, or application-progress framework.

## A. P0 Product Contract

RunSentry launches one command, mirrors its stdout/stderr, observes the root process and discoverable descendants, samples local resources and watched paths, writes JSONL telemetry, and makes a conservative deterministic health assessment. It never automatically kills, restarts, pauses, reprioritizes, or recovers the workload. Forwarding a user-delivered signal is the only control action.

It promises observable facts, not application truth. It does not promise to find every deadlock, discover daemonized/escaped descendants, know every child exit code, predict OOM exactly, predict total disk use, provide job-completion ETA without a total, or reattach after its own crash. Unavailable evidence is `UNKNOWN`, not invented confidence.

## B. CLI Contract

```text
runsentry run --name JOB_NAME [--watch PATH]... [--interval SECONDS]
              [--output-dir PATH] -- COMMAND [ARG]...
```

- `--name` is required, nonempty, and a telemetry/display label only.
- `--watch PATH` is repeatable. A missing path is valid and retried.
- `--interval SECONDS` defaults to `5.0`, range `1.0`–`60.0`; it controls sampling, not output forwarding.
- `--output-dir PATH` defaults to `./runsentry-<run_id>`, containing `telemetry.jsonl` and `summary.json`; a pre-existing nonempty directory is an error.
- `--` is mandatory. Every following token is exact workload argv, including option-looking tokens. Empty argv is a usage error.
- P0 is direct execution only: `subprocess.Popen(argv, shell=False)`. RunSentry never quotes, expands, globs, redirects, builds pipes, or parses shell syntax. There is no `--shell`.

Shell users explicitly make the shell the command, for example:
`runsentry run --name x -- bash -lc 'python3 job.py | tee output.log'`.
They own quoting, shell availability, and shell-language semantics; that shell is the observed root. `bash` is common but not guaranteed, and `/bin/sh -c` has different semantics.

Exit codes: `0` successful observed lifecycle; `2` pre-launch usage/config error; `3` observer/persistence degradation that prevents reliable normal result; `4` wrapped lifecycle failed; `130` SIGINT received and forwarded. Underlying root exit is recorded when known. Root zero with live known descendants is not successful yet.

## C. Process Supervision Model

RunSentry owns a root child handle but is an observer, not a process manager. It records root PID, create time, argv, monotonic start, and process group/session where available. Process identity is `(pid, create_time)`; changed create time means PID reuse and is never accepted.

While the root identity exists, recursive psutil descendants are sampled. Every seen descendant is retained by identity. After root exit, retained identities are sampled individually because reparenting breaks recursive root discovery. Children created and exited between samples, inaccessible children, and daemonized/escaped children may be missed. That is recorded as a limitation, not guessed. Zombie status is evidence of lifecycle change but normally provides no reliable nonzero exit code.

| Observable condition | Deterministic lifecycle result | Handling |
|---|---|---|
| Root exits 0; no known live descendants | `COMPLETE` | Emit `ROOT_EXIT_ZERO`, bounded pipe drain, final summary. |
| Root exits nonzero/signal; no known live descendants | `FAILED` | Emit root failure fact, bounded drain, final summary. |
| Root exits 0; known descendants live | `ROOT_EXITED_WAITING_DESCENDANTS`, not complete | Observe retained identities without killing. Complete only after all known live descendants exit/disappear without PID reuse. |
| Root exits nonzero/signal; descendants live | `FAILED` immediately | Warn descendants remain; drain pipes at most 30 seconds; exit without killing. |
| Child disappears/crashes while root lives | informational only | Emit `CHILD_DISAPPEARED` or `CHILD_ZOMBIE_OBSERVED`; root remains authority. |
| Descendants survive root disappearance | waiting phase after root success; warning after root failure | Do not rediscover after reparenting; observe retained identities only. |

A child event causes final `FAILED` only when it is reflected in the wrapped root's observable failure. A shell root may propagate a child failure, but that is shell behavior. Child disappearance is a process-change activity signal, never failure or stall evidence alone.

The root starts a new Unix process group/session where supported. SIGINT/SIGTERM received by RunSentry is recorded and forwarded once to that group (or root if unavailable), followed by a brief drain and best-effort summary; RunSentry never escalates to SIGKILL. If RunSentry crashes, pipe closure can harm the workload; P0 has no reattach/crash-resilient output guarantee.

## D. Telemetry Schema and Durability

`telemetry.jsonl` is UTF-8 JSONL: one serialized object plus newline per completed write. Every event has `schema_version: "1.0"`, `event_type`, UUID4 `run_id`, RFC3339 UTC `timestamp`, monotonic `elapsed_s`, and `health_state`. Minor versions add optional fields; major versions may change meaning. Unknown fields are `null`.

Sample events include:

```text
root: {pid, create_time_epoch_s, alive, lifecycle_phase}
process_tree: {count, known_count, cpu_percent, rss_bytes, cpu_user_s, cpu_system_s}
system_memory: {total_bytes, available_bytes, percent_used}
swap: {total_bytes, used_bytes, percent_used}
streams: {stdout_bytes, stderr_bytes, stdout_last_activity_elapsed_s,
          stderr_last_activity_elapsed_s, stdout_bytes_since_last, stderr_bytes_since_last}
watches: [{configured_path, resolved_path, kind, status, size_bytes,
           size_delta_bytes, file_count, file_count_delta, mtime_epoch_s,
           mtime_changed, filesystem_free_bytes, filesystem_usable_bytes}]
throughput: {basis, current_rate_per_s, window_rate_per_s,
             job_completion_eta_s, disk_exhaustion_eta_s, confidence}
warnings: [reason_code]
reasons: [reason_code]
```

`cpu_percent` is aggregate and may exceed 100 on multicore machines; it is null for its first interval. `count` is live known identities; `known_count` is identities with readable metrics. State-transition events add `from_state`, `to_state`, `reasons`, and `evidence_window_s`. Lifecycle events add `lifecycle` (`RUN_STARTED`, `ROOT_EXITED`, `ROOT_EXITED_WAITING_DESCENDANTS`, `SIGNAL_RECEIVED`, `OBSERVER_DEGRADED`, `OUTPUT_DRAIN_COMPLETE`) and known exit detail. A final `final_summary` event embeds the same object as `summary.json`.

Serialize fully before writing, append one line where practical, and flush each event. Per-event `fsync` is not required. Abrupt crash may leave a truncated final line; readers must ignore an unparsable final line and preserve earlier completed records. On write/flush failure including disk full, issue one best-effort stderr diagnostic, mark telemetry failed, abandon later sink writes, and continue draining/observing the workload. Summary failure is recorded and never intentionally terminates the workload.

P0 reason codes: `ROOT_RUNNING`, `ROOT_EXIT_ZERO`, `ROOT_EXIT_NONZERO`, `ROOT_SIGNALED`, `CHILD_DISAPPEARED`, `CHILD_ZOMBIE_OBSERVED`, `DESCENDANTS_REMAIN_AFTER_ROOT_EXIT`, `STARTUP_WINDOW`, `RECENT_CPU_ACTIVITY`, `RECENT_STREAM_ACTIVITY`, `RECENT_WATCH_ACTIVITY`, `RECENT_PROCESS_CHANGE`, `QUIET_NO_CONTRARY_EVIDENCE`, `MULTI_SIGNAL_INACTIVITY`, `METRICS_INSUFFICIENT`, `HIGH_MEMORY_PRESSURE`, `SUSTAINED_RSS_GROWTH`, `SWAP_PRESSURE`, `POSSIBLE_OOM_RISK`, `LOW_DISK_SPACE`, `DISK_EXHAUSTION_RISK`, `WATCH_INACCESSIBLE`, `TELEMETRY_WRITE_FAILED`, `SUMMARY_WRITE_FAILED`, `OUTPUT_CAPTURE_FAILED`, `OBSERVER_METRIC_UNAVAILABLE`.

## E. stdout / stderr Observation Design

P0 uses two separate OS pipes and starts one reader thread per pipe before material child output. Each reads fixed-size **binary** chunks, immediately forwards raw bytes to the matching inherited output destination, and atomically updates byte totals/activity time. It never decodes Unicode, parses lines, retains text, stores transcripts, or queues unbounded output. Binary output, invalid Unicode, and partial lines are safe.

Separate continuous readers prevent one pipe filling and starving the other. Forwarding can block only when the inherited terminal/output destination blocks; RunSentry adds no memory buffer. On destination failure, it records the failure and keeps draining/discarding where possible. Within-stream order is preserved; cross-stream ordering is inherently unavailable. P0 does not proxy stdin.

PTY is explicitly out of scope. TTY-sensitive programs may change buffering, color, prompts, or behavior under pipes and are unsupported for faithful execution. Program-side buffering makes silence non-evidence. Inherited pipe descriptors in descendants can delay EOF; RunSentry crash can close pipes.

## F. Watched Path Model

Portable polling uses `os.stat`, `os.walk`, and `shutil.disk_usage`, not platform event APIs.

- A regular file reports size, successful-sample delta, and mtime activity. Inode where available, or size/mtime discontinuity, identifies replacement/rotation. Shrink, replacement, and deletion are activity, never negative throughput.
- A directory reports recursive aggregate regular-file bytes/count and maximum descendant mtime. Directory symlinks are not followed; symlink files do not count as regular bytes.
- Missing paths are `PENDING`; deleted paths are `MISSING`; both are retried and may later appear normally.
- Inaccessible paths have null metrics and a warning, never failure or quiet evidence.

Free/usable bytes are sampled per accessible watched filesystem. Large recursive scans can be expensive and mounted filesystem semantics vary; users should watch narrow outputs. This is snapshot polling, not an event guarantee.

## G. Health State Machine

States: `STARTING`, `HEALTHY`, `QUIET`, `SUSPECTED_STALL`, `FAILED`, `COMPLETE`; the last two are terminal. `ROOT_EXITED_WAITING_DESCENDANTS` is lifecycle phase, not a seventh health state. Retained descendants supply activity during that phase.

Centralized internal defaults, not CLI options: startup 30 s; quiet entry 60 s with at least three samples; stall consideration 180 s with at least three samples. Later advanced configuration may expose constants only without changing these semantics.

`HEALTHY` means recent observable activity. `QUIET` means little observable activity but insufficient evidence of abnormality; it is neither warning nor predicted stall. `SUSPECTED_STALL` means multiple independent observable channels jointly show lack of progress for the entire stall window; it is recoverable, not confirmed deadlock.

Activity is positive CPU-time delta, stdout/stderr bytes, watched-path size/count/mtime change, or membership change. A stall requires every applicable channel readable and quiet: CPU-time, both stream counters, membership, and at least one successfully sampled watch if watches were supplied. With no `--watch`, CPU, streams, and membership suffice. Unavailable process metrics/stream accounting or an inaccessible supplied watch makes evidence incomplete and prevents a stall. No one signal can cause a stall.

| Transition | Evidence | Recovery / competing evidence |
|---|---|---|
| `STARTING → HEALTHY` | Lifecycle alive and any activity after initial sample | N/A |
| `STARTING → QUIET` | Startup elapsed, three samples, no activity for 60 s, but evidence incomplete or under 180 s | Any activity → healthy; gaps retain quiet + `METRICS_INSUFFICIENT` |
| `HEALTHY → QUIET` | Three samples and 60 s with no activity | Any activity keeps/returns healthy |
| `STARTING`/ `QUIET → SUSPECTED_STALL` | Three samples spanning 180 s; all applicable channels readable/quiet; lifecycle alive | Any activity → healthy; required metric gap → quiet |
| `SUSPECTED_STALL → HEALTHY` | Any activity | Historical suspicion retained |
| any nonterminal → `COMPLETE` | Root zero and no known live descendant | Child history remains |
| any nonterminal → `FAILED` | Root nonzero/signal | Lifecycle fact, not heuristic |

| Required case | Result |
|---|---|
| CPU near zero, streams silent, watch unchanged, sleeping normally | `QUIET` after 60 s; stall only after full 180 s readable multi-signal window. Sleep status proves neither health nor failure. |
| CPU high, streams silent, file unchanged | `HEALTHY`: CPU advance competes. |
| CPU low, stdout active | `HEALTHY`: stream activity competes. |
| CPU low, streams silent, file growing | `HEALTHY`: watch activity competes. |
| Lifecycle alive, all applicable signals inactive long enough | stall only after full complete-evidence window. |
| Process metrics temporarily unavailable | `STARTING`/ `QUIET` + `METRICS_INSUFFICIENT`, never stall. |
| No `--watch` | Valid: CPU, streams, membership define eligibility; lack of a watch is not a signal. |

## H. Memory / Possible OOM Risk

Report tree RSS/peak RSS, sustained 60-second RSS trend, total/available memory, and swap use/trend. `HIGH_MEMORY_PRESSURE` requires known available memory below 10%; `SUSTAINED_RSS_GROWTH` requires sustained positive growth; `SWAP_PRESSURE` requires material use or sustained growth. `POSSIBLE_OOM_RISK` requires all three categories. It is a bounded warning, never time-to-OOM, prediction, health failure, or reason to control a workload. Cgroups, memory compression, other processes, limits, and OS policy remain outside inference.

## I. Disk Exhaustion Risk

Disk exhaustion ETA is per watched filesystem and is `UNKNOWN` unless target filesystem and usable free bytes are known, a watch maps to it, at least three positive-growth samples span 60 seconds, and sustained rate is positive. Estimate `usable_free_bytes / conservative_rate`, where rate is max(latest positive rate, 60-second mean). Warn `LOW_DISK_SPACE` below 5% usable free and `DISK_EXHAUSTION_RISK` only for valid estimate under 24 h. Rotation, shrinking, inaccessibility, other writers, another filesystem, and insufficient history are unknown. This is not completion ETA or total-machine prediction.

## J. Throughput and ETA

Throughput is an observable trend, not task progress. Select one basis in order: watched regular-file bytes, watched-directory bytes, directory file count, stdout bytes, stderr bytes. Report current and 60-second rates plus basis/confidence; ambiguous/nonpositive rate is unknown.

`job_completion_eta_s` is always null in P0. No completion total/progress protocol exists, and file growth never proves completion percentage. `disk_exhaustion_eta_s` is a distinct evidence-limited result from section I. No rate or elapsed time becomes job ETA.

## K. Final Run Summary

`summary.json` and final JSONL contain:

```text
schema_version, run_id, name, command_argv, started_at, ended_at, duration_s,
final_status (COMPLETE|FAILED|INTERRUPTED|OBSERVER_DEGRADED),
root_pid, root_create_time_epoch_s, root_exit_code, root_exit_signal,
lifecycle_phase_at_end, peak_root_rss_bytes, peak_process_tree_rss_bytes,
process_tree_peak_count, cpu_user_s, cpu_system_s, peak_cpu_percent,
stdout_bytes, stderr_bytes, stdout_last_activity_elapsed_s,
stderr_last_activity_elapsed_s, watches_final, watched_growth_bytes,
watched_growth_file_count, warnings, observer_errors,
health_transition_history, descendant_lifecycle_observations,
throughput: {basis, peak_rate_per_s, final_window_rate_per_s,
             job_completion_eta_s, disk_exhaustion_estimates}, completion_reason
```

`completion_reason` is `ROOT_EXIT_ZERO`, `ROOT_EXIT_NONZERO`, `ROOT_SIGNALED`, or `WRAPPER_INTERRUPTED`. Unavailable metrics are null with observer errors. Summary failure must not intentionally stop a workload.

## L. Internal Module Architecture

Future package layout is deliberately small:

```text
runsentry/
  __init__.py   version only
  cli.py        parsing and exit mapping
  runner.py     Popen lifecycle, signals, explicit main loop
  streams.py    bounded binary drains/counters
  process.py    psutil identities, snapshots, retained descendants
  watch.py      portable watches/disk
  sampler.py    monotonic scheduling/normalized samples
  health.py     centralized constants and pure transitions
  telemetry.py  JSONL and summary persistence
  models.py     small shared dataclasses/enums
```

No plugins, event bus, DI framework, abstract factories, database, or web layer.

## M. Failure Semantics

The workload takes precedence over observation. psutil errors, permissions, process races, inaccessible watches, disk-info failure, and temporary system failures produce null fields/reason codes and continue. Identity mismatch never matches the original process. Output-capture setup failure before launch prevents launch; post-launch reader failure records `OUTPUT_CAPTURE_FAILED`, then attempts drain/discard without killing the child.

Telemetry/summary failure after launch degrades the observer, not the workload. Return `3` after lifecycle only when a reliable normal result cannot be produced; record root failure separately. User interruption returns `130`. Enumeration is a snapshot, not ancestry proof.

## N. Synthetic Test Acceptance Matrix

Time may be scaled, but 30/60/180 relative semantics must remain.

| Scenario | Expected sequence | Must not occur | Warnings | Final result / test failure |
|---|---|---|---|---|
| `healthy_cpu.py` | starting → healthy → complete | quiet, stall, failed | none | Root 0; fail if CPU not counted. |
| `healthy_io.py` | starting → healthy → complete | stall, failed | none | Root 0; fail if stream/watch activity missing. |
| `quiet_but_healthy.py` | starting → quiet → complete | stall, failed | quiet reason only | Root 0 before stall window; fail if silence alone stalls. |
| `memory_growth.py` | starting → healthy → complete | failed/stall solely from memory | sustained growth; pressure/risk only when thresholds met | Script result; fail if deterministic OOM claim or unsupported warning. |
| `hang_after_60s.py` | starting → healthy/quiet → suspected stall, then interrupt | failed before root ends; early stall | multi-signal inactivity | Interrupted; fail if no stall after full window or early stall. |
| `crash_after_60s.py` | starting → healthy/quiet → failed | complete | root nonzero | Root nonzero; fail if inferred before exit or missing status. |
| `child_process_crash.py` | root remains healthy/quiet, then root-defined terminal | failed solely for child disappearance | child disappearance/zombie if observable | Root 0 complete, root nonzero failed; fail if child overrides root. |
| `disk_writer.py` | starting → healthy → complete | stall, failed | growth; disk warning only with prerequisites | Script result; fail if estimate lacks known fs/free/history. |

## O. Sentinel Dogfood Plan

Run non-sensitive Sentinel jobs unchanged through RunSentry in shadow observation: same command, cwd, inputs, schedule, and human procedure; no control authority. Keep telemetry local and redact paths/argv before sharing.

Record human timestamps for healthy, planned quiet, suspected/confirmed stall, resource concern, and terminal result. A false positive is a RunSentry stall without confirmed human stall; a miss is confirmed human stall without prior RunSentry stall; record delay. Score only non-null disk ETA against reality; job ETA coverage is deliberately zero. Review resource-warning usefulness/noise across CPU, I/O, quiet, multiprocess, and failure runs; do not tune from one job.

## P. P0 Acceptance Criteria

GO requires macOS and Linux passing section N; no pipe deadlock or unbounded output retention; correct root/signal/live-descendant lifecycle; no single-signal stalls; degraded metrics/sinks never intentionally killing active workload; parseable completed JSONL records (one truncated final line allowed after forced crash); matching summary when writes succeed; and ten representative Sentinel shadow runs without observer-caused failure or unacceptable false stalls. Any breach is NO-GO.

## Q. Implementation Sequence

| Task | Purpose, artifacts, tests, acceptance |
|---|---|
| RS-P0-002 | Metadata/package skeleton; smoke tests; Python 3.10 install/import on both OSes. |
| RS-P0-003 | Direct-exec CLI; exact `--` argv/no-shell tests; contract exactness. |
| RS-P0-004 | Runner/session/signals/bounded drains; stream stress tests; no deadlock/buffering. |
| RS-P0-005 | PID identity and retained descendants; race/child tests; section-C lifecycle table. |
| RS-P0-006 | Watches/disk snapshots; file/directory/rotation/access tests; nullable portability. |
| RS-P0-007 | JSONL/summary/failure handling; parse/failure tests; durability semantics. |
| RS-P0-008 | Pure health/resource/throughput rules; table tests; no-single-signal invariant. |
| RS-P0-009 | Eight synthetic workloads; both-OS section-N acceptance. |
| RS-P0-010 | Sentinel shadow dogfood/release checklist; section-P gates. |

## R. Architecture Risk Register

| Rank | Risk | Severity | Likelihood | Mitigation |
|---:|---|---|---|---|
| 1 | Pipe blocking/deadlock under high dual-stream output | Critical | Medium | Two binary drains/no unbounded queue/stress gate. |
| 2 | False stall for legitimate quiet/waiting work | High | High | Complete evidence/180 s/dogfood review. |
| 3 | PID reuse, reparenting, missed descendants | High | Medium | PID/create-time, retained identities, explicit limits. |
| 4 | macOS/Linux process and signal differences | High | Medium | Both OS tests; null rather than guess. |
| 5 | Misleading throughput/disk ETA | High | High | Strict prerequisites/job ETA null. |
| 6 | OOM warning mistaken for prediction | Medium | Medium | Bounded language/combined evidence. |
| 7 | Large directory scans perturb workload | Medium | Medium | Snapshot polling/narrow-watch documentation. |
| 8 | Observer crash closes child pipes | Medium | Low | Explicit limitation/no crash-resilience claim. |

## Frozen P0 Decisions and Scope Assessment

1. No `--shell`; direct exec only; users invoke shells themselves.
2. Health constants are centralized conservative internals; no P0 tuning surface.
3. Root-zero with tracked live descendants remains in waiting lifecycle, not complete, until retained descendants end.
4. PTY is out of scope; two bounded binary pipe drains are P0 output handling.
5. Job completion ETA is null/unknown; throughput and disk ETA are distinct.

This P0 is small enough for one developer with AI assistance to maintain if these boundaries remain intact.

