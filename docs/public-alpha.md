# RunSentry Public Alpha Notes

RunSentry P0 is ready for a conservative GitHub public alpha positioning as a local
observer for long-running commands.

## What it is

RunSentry wraps one local command and records factual observations:

- process lifecycle and resource facts;
- stdout/stderr activity counters;
- watched file/directory facts;
- local disk usage facts for watched paths;
- JSONL telemetry;
- a final JSON summary;
- conservative health states.

It is useful for local shell commands, Python jobs, data-processing jobs, and local
agent/AI workloads where the user wants a lightweight observer.

## What it is not

RunSentry P0 is not:

- a workflow orchestrator;
- a production supervisor;
- an OOM predictor;
- a disk exhaustion predictor;
- a job ETA engine;
- a notification service;
- a dashboard or SaaS product;
- an AI/LLM judgment layer;
- an automatic kill/recovery system.

## Safe alpha expectations

Users should expect local artifacts under:

```text
.runsentry/runs/<run_id>/
```

Each run contains:

- `telemetry.jsonl`
- `summary.json`

RunSentry does not store stdout/stderr content and does not upload telemetry. It does
store command argv and local paths as factual launch/run data.

## Health wording

`SUSPECTED_STALL` means conservative suspicion only. It requires multiple independent
available inactivity signals over a sustained window. Silence alone is not enough.

`QUIET` is a valid non-alarming state for workloads that are alive but not visibly active.

Unavailable process, output, or watched-path facts reduce confidence rather than
increasing suspicion.

RunSentry never automatically kills or recovers workloads in P0.

## Known alpha limitations

- macOS and Linux only.
- No Windows support promise.
- Process/resource observations can be partial due to OS permissions.
- Short jobs may show only `STARTING -> COMPLETE`.
- Conservative health rules may miss real stalls.
- Watched-path creation is visible as a changed path, but numeric deltas can be `null`
  when there was no previous measurable size.
- Directory watching uses polling and recursive scans; very large trees can make samples
  slower.
- No hosted telemetry, dashboards, notifications, or multi-machine monitoring.

## Minimal examples

```bash
runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
```

```bash
runsentry run --name io-demo --watch out.log -- python3 job.py
```

```bash
runsentry run --output-dir /tmp/runsentry-demo -- python3 job.py
```
