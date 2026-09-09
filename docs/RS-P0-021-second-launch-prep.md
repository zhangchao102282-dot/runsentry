# RS-P0-021 Second Launch Prep

Date: 2026-09-09

## Demo Assets

- README GIF: `docs/assets/runsentry_demo_readme.gif`
- README GIF size: 462117 bytes
- External-sharing MP4: `docs/assets/runsentry_demo_final.mp4`
- External-sharing MP4 size: 251587 bytes

The README embeds only the GIF. The MP4 remains a repository asset for external sharing.

## README Placement

The README now puts the visual demo near the top:

1. Project title
2. One-sentence positioning
3. `pip install runsentry`
4. Minimal `runsentry run ...` command
5. Visual demo GIF
6. What RunSentry records
7. Safety/non-goals

## Show HN

Title:

```text
Show HN: RunSentry – A local health observer for long-running commands
```

Post:

```text
RunSentry is a small local CLI that wraps one long-running command and records factual
evidence about what happened while it ran.

It does not modify the child program. It launches the command directly, preserves
stdout/stderr output, observes process/resource activity, tracks watched file or
directory changes, and writes local JSONL telemetry plus a final summary.json.

The P0 scope is intentionally conservative:

- no daemon
- no cloud
- no automatic killing or recovery
- no PTY or dashboard
- conservative health states rather than guaranteed hang detection

Install:

pip install runsentry

Example:

runsentry run --name demo -- python my_script.py

I built it for local development, research, and agent/AI jobs where a command may run for
minutes or hours and I want a lightweight record of whether it was active, quiet,
completed, or failed.
```

## Reddit

Suggested title:

```text
I built RunSentry, a local observer for long-running commands
```

Post:

```text
I built a small Python CLI called RunSentry for watching long-running local commands
without changing the command itself.

You run:

pip install runsentry
runsentry run --name demo -- python my_script.py

RunSentry launches the child command directly and keeps stdout/stderr visible. It records
process/resource facts, stdout/stderr activity counters, watched file/directory changes,
local JSONL telemetry, conservative health states, and a final summary.json.

What it is not:

- not a daemon
- not cloud/SaaS
- not a supervisor
- does not automatically kill or restart anything
- does not guarantee hang detection

The current alpha is intentionally local-first and conservative. The main thing I want to
learn from real users is whether the summary and telemetry are useful when a command runs
for minutes or hours and you do not want to babysit it.
```

## DEV Community

Suggested title:

```text
RunSentry: a lightweight local observer for long-running commands
```

Post:

```text
RunSentry is a lightweight CLI for observing long-running local commands.

It wraps a command without modifying it:

pip install runsentry
runsentry run --name demo -- python my_script.py

RunSentry records factual local evidence:

- process/resource activity
- stdout/stderr activity
- watched file/directory changes
- local JSONL telemetry
- a final summary.json
- conservative health states such as QUIET, SUSPECTED_STALL, FAILED, and COMPLETE

It is deliberately small:

- no daemon
- no cloud
- no automatic killing
- no restart/recovery behavior
- no production-supervisor claims

The latest alpha, 0.1.0a2, fixes output tee latency so small flushed progress lines from
child processes appear promptly while RunSentry is observing them.
```

## Notes

- Do not claim guaranteed hang detection.
- Do not ask for stars.
- Lead with the demo GIF where the platform allows media.
- Use the MP4 asset for platforms where a GIF is too large or awkward.
