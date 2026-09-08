# RS-P0-016 Demand Validation Launch Pack

## One-sentence pitch

RunSentry is a lightweight local observer that wraps long-running commands and tells
you whether they are active, quiet, completed, failed, or conservatively suspicious.

## Short GitHub description

Lightweight local health observer for long-running commands and Python jobs.

## Target users

- Developers running long shell commands or Python jobs.
- Data and research users running local batch scripts.
- Local AI/agent users running tool-heavy jobs that may go quiet for long periods.
- Maintainers who want factual local telemetry without adopting a workflow platform.

## Use cases

- Wrap a long-running Python script and inspect local `summary.json` afterward.
- Watch stdout/stderr activity without storing output content.
- Watch an output file or directory for factual growth.
- Check process/resource facts after a run.
- Distinguish a quiet workload from a conservatively suspected stall.
- Share a sanitized summary when asking for debugging help.

## Non-goals

RunSentry P0 is not:

- a production supervisor;
- a guaranteed stuck-process detector;
- an OOM predictor;
- a disk exhaustion predictor;
- a job ETA engine;
- a workflow orchestrator;
- a notification service;
- a dashboard or SaaS product;
- an automatic kill/recovery system.

## Safe demo command

```bash
runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
```

Demo with a watched path:

```bash
runsentry run --name io-demo --watch out.log -- python3 job.py
```

## Feedback questions

- Did install from source work on your machine?
- What OS and Python version did you use?
- What kind of command did you wrap?
- Did the health state match your own judgment?
- Was `summary.json` useful enough to inspect after the run?
- Were the privacy warnings clear?
- What missing fact or feature blocked real use?
- Would PyPI packaging materially reduce friction?
- Would notifications or a remote view matter for your use case?
- Would you use this weekly?

## Success metrics

Signals to track during the first validation window:

- non-owner clone/install attempts;
- GitHub stars from users outside the original development context;
- issues with sanitized summaries;
- repeat users;
- feature requests that fit the local-observer model;
- requests for notification, remote, or multi-machine capabilities;
- willingness-to-pay or organizational-use signals.

## Places to share

Share in small, relevant places first:

- personal GitHub/network post;
- Hacker News `Show HN`;
- Python developer communities;
- data engineering or local automation communities;
- local AI/agent developer circles;
- small private messages to developers who run long scripts.

Avoid broad spam posting. Ask for concrete feedback rather than promotion.

## Suggested GitHub topics

- `python`
- `cli`
- `monitoring`
- `observability`
- `watchdog`
- `long-running-jobs`
- `process-monitor`
- `local-first`
- `telemetry`
- `ai-agents`

## Suggested first 7-day validation plan

Day 1:

- Share with 3-5 trusted developers who run long local jobs.
- Ask each person to install from source and run one safe local command.

Day 2:

- Post one concise public announcement.
- Watch for install friction and README confusion.

Day 3:

- Review any issues and sanitized summaries.
- Classify feedback as bug, wording issue, missing P0 fact, or future-scope request.

Day 4:

- Try one additional real-world local dogfood run.
- Compare RunSentry output against human judgment.

Day 5:

- Share a short follow-up with one concrete example summary, sanitized.

Day 6:

- Count non-owner installs/clones if visible, stars, issues, and direct replies.
- Identify repeated feature requests.

Day 7:

- Decide whether demand validation is strong enough to plan the next P0 polish task.
- Do not expand into SaaS, remote monitoring, prediction, or auto-intervention without a
  separate product decision.

