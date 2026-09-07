# RS-P0-012 GitHub Public Alpha Launch Prep

## Launch recommendation

`READY_TO_CREATE_GITHUB_REPO`

RunSentry is ready to prepare manually for a conservative GitHub public alpha. This
task did not create the GitHub repository, push to GitHub, publish to PyPI, or create
a release tag.

## Public positioning

Recommended positioning:

> RunSentry is a lightweight local observer for long-running commands, Python jobs,
> and AI-agent style local tasks.

Core message:

- wraps any command after an explicit `--` boundary;
- observes stdout/stderr activity without storing output content;
- observes process/resource facts;
- observes watched file/directory growth and disk facts;
- writes local JSONL telemetry and `summary.json`;
- provides conservative health states;
- never automatically kills or recovers workloads;
- stays local-only with no network upload.

Avoid positioning RunSentry as:

- a guaranteed stuck-process detector;
- an OOM predictor;
- a disk exhaustion predictor;
- an ETA engine;
- a workflow framework;
- a production supervisor;
- a SaaS platform;
- a replacement for Prefect, Dagster, or Temporal;
- a Kubernetes observability product.

## Recommended GitHub metadata

Repository name:

`runsentry`

Short description:

`Lightweight local health observer for long-running commands and Python jobs.`

Suggested topics:

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

Avoid misleading topics:

- `kubernetes`
- `saas`
- `mlops`
- `workflow-orchestration`

## README final review

README status: ready.

The README now includes:

- what RunSentry is;
- public alpha status;
- current P0 capabilities;
- source installation;
- quick-start usage;
- explicit `--` command boundary;
- `--watch` examples;
- local output artifact path;
- health states;
- safety model;
- telemetry privacy/locality;
- limitations and non-goals;
- bug-reporting guidance;
- license.

The README intentionally avoids fake badges, fake benchmarks, fake users,
Sentinel-specific examples, SaaS positioning, or production-supervisor claims.

## Public alpha document review

`docs/public-alpha.md` status: ready.

It documents:

- public alpha scope;
- current capabilities;
- non-goals;
- safe alpha expectations;
- local telemetry behavior;
- artifact sanitization guidance;
- health-state wording;
- known limitations;
- useful alpha feedback;
- GO/KILL signals for continuing the project.

No private Sentinel details are included.

## Security and privacy notes

Public docs now state:

- telemetry is local;
- no telemetry is uploaded;
- stdout/stderr content is not stored;
- stdout/stderr counters and activity facts are stored;
- command argv is stored and may contain sensitive values;
- local paths are stored and may reveal local information;
- generated `.runsentry/` artifacts should not be committed;
- users should sanitize `summary.json` before sharing it publicly.

## Manual launch checklist

Do not run network/destructive commands automatically from an agent task. Execute these
manually when ready.

1. Confirm local repository state:

   ```bash
   cd /Users/zhangchao/ai-lab/runsentry
   git status
   .venv/bin/python -m pytest -q
   ```

2. Create the GitHub repository manually:

   - name: `runsentry`;
   - visibility: public when ready;
   - description: `Lightweight local health observer for long-running commands and Python jobs.`;
   - topics: `python`, `cli`, `monitoring`, `observability`, `watchdog`,
     `long-running-jobs`, `process-monitor`, `local-first`, `telemetry`, `ai-agents`.

3. Add the remote manually after the repository exists:

   ```bash
   git remote add origin git@github.com:<OWNER>/runsentry.git
   ```

4. Push `main` manually:

   ```bash
   git push -u origin main
   ```

5. Inspect rendered GitHub pages:

   - README rendering;
   - `docs/public-alpha.md`;
   - issue templates;
   - license display;
   - Actions workflow detection.

6. Verify CI after push:

   - Ubuntu Python 3.10;
   - Ubuntu Python 3.11;
   - Ubuntu Python 3.12;
   - macOS Python 3.12.

7. Optionally create the first tag manually after CI passes:

   ```bash
   git tag -a v0.1.0-alpha.1 -m "RunSentry v0.1.0-alpha.1"
   git push origin v0.1.0-alpha.1
   ```

8. Optionally create the first GitHub release manually from that tag.

9. Later, verify clone/install on a clean machine:

   ```bash
   git clone git@github.com:<OWNER>/runsentry.git
   cd runsentry
   python -m pip install -e ".[test]"
   python -m pytest -q
   runsentry --help
   runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
   ```

## First tag and release plan

Recommended first tag:

`v0.1.0-alpha.1`

Recommended release title:

`RunSentry v0.1.0-alpha.1`

Draft release notes:

````markdown
RunSentry v0.1.0-alpha.1 is the first conservative public alpha.

RunSentry is a lightweight local observer for long-running commands and Python jobs.

Included P0 capabilities:

- direct command wrapping after an explicit `--` boundary;
- `shell=False` execution semantics;
- stdout/stderr byte-preserving tee with activity counters;
- process/resource fact snapshots;
- watched file/directory facts;
- local disk facts for watched paths;
- local JSONL telemetry;
- final `summary.json`;
- conservative health states: STARTING, HEALTHY, QUIET, SUSPECTED_STALL, FAILED,
  COMPLETE;
- synthetic scenario validation and local dogfood runs.

Important limitations:

- local-only;
- macOS/Linux target;
- no Windows support promise;
- no dashboard or SaaS;
- no notifications;
- no automatic kill or recovery;
- no OOM prediction;
- no disk exhaustion prediction;
- no generic job ETA;
- health states are conservative and may miss real stalls.

Install from source for now:

```bash
python -m pip install -e .
```
````

Do not publish to PyPI until a separate packaging/release task explicitly authorizes it.

## Example commands checked

Public examples are intentionally small and safe:

```bash
runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
```

```bash
runsentry run --name io-demo --watch out.log -- python3 job.py
```

```bash
python -m runsentry run --name demo -- python -c "import time; time.sleep(2)"
```

The first example was smoke-tested with the repository virtual environment and an
ignored `.runsentry/` output directory.

## Validation performed

Validation commands:

```bash
.venv/bin/python -m py_compile src/runsentry/*.py
.venv/bin/python -m pytest -q
.venv/bin/runsentry --help
.venv/bin/runsentry run --help
.venv/bin/runsentry run --output-dir .runsentry/launch-prep-smoke --name demo -- .venv/bin/python -c "import time; time.sleep(0.1)"
```

Observed result:

- Python version: 3.12.14;
- pytest result: 106 passed, 3 skipped;
- smoke command exit code: 0;
- smoke run directory:
  `.runsentry/launch-prep-smoke/runs/20260907T205234Z-6a83e6ea9463/`;
- smoke final health state: `COMPLETE`;
- smoke telemetry line count: 3;
- forbidden prediction/intervention fields were absent from the smoke summary;
- generated `.runsentry/` artifacts remained ignored.

## Changes made

Created:

- `docs/RS-P0-012-github-launch-prep.md`.

Modified:

- `README.md`;
- `docs/public-alpha.md`.

Runtime code was not changed.

## Remaining notes

- Remote GitHub CI must be checked after the first push.
- A clean-machine clone/install validation should be done after the public repository
  exists.
- Keep public messaging conservative; do not let `SUSPECTED_STALL` become a claim of
  certainty.

## Final launch recommendation

`READY_TO_CREATE_GITHUB_REPO`
