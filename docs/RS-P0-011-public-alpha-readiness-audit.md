# RS-P0-011 Public Alpha Readiness Audit

## Readiness verdict

RunSentry P0 is ready for a conservative GitHub public alpha.

Recommendation:

`READY_FOR_PUBLIC_ALPHA`

This recommendation applies only to the current P0 scope: a local observer for one
long-running command with conservative health states and local telemetry artifacts.
It does not imply production-supervisor readiness, prediction guarantees, remote
monitoring, notifications, or automatic intervention.

## README findings

Before this audit, the README still described an earlier scaffold/resource-observation
state and incorrectly implied that watched paths, telemetry, and health states were
not yet implemented. That would confuse early GitHub users.

The README was revised to document:

- what RunSentry is;
- current P0 capabilities;
- installation from source;
- basic `runsentry run ... -- COMMAND [ARG ...]` usage;
- `--watch` usage;
- explicit shell behavior;
- local output artifacts;
- health state meanings;
- P0 limitations and non-goals.

The README does not include fake badges, fake benchmarks, fake users, pricing, SaaS
claims, or Sentinel-specific examples.

## CLI help findings

The CLI already exposed the required small surface:

- `runsentry --help`;
- `runsentry run --help`;
- `--name`;
- `--watch`;
- `--output-dir`;
- `--interval`;
- explicit `--` command boundary.

The help wording was clarified to describe RunSentry as a local conservative observer
and to make the post-`--` child argv boundary clearer. No CLI options were added.

## Packaging findings

`pyproject.toml` remains standards-based and minimal:

- build backend: setuptools;
- package name: `runsentry`;
- version: `0.0.1.dev0`;
- Python requirement: `>=3.10`;
- console entry point: `runsentry = runsentry.cli:main`;
- runtime dependency: `psutil>=5.9`;
- test extra: `pytest>=7`.

The development-status classifier was updated from pre-alpha to alpha to match the
public-alpha readiness position. No new dependency was added.

## Gitignore and artifact findings

`.gitignore` covers the generated and local-development artifacts relevant to P0:

- `.runsentry/`;
- `.venv/`;
- `venv/`;
- `__pycache__/`;
- `*.py[cod]`;
- `.pytest_cache/`;
- build/dist/egg-info outputs;
- `.DS_Store`.

Tracked-file inspection did not show generated dogfood artifacts, `.runsentry` output,
temporary run output, secrets, token files, credential files, or `.env` files.

## Telemetry privacy and locality findings

The public-facing docs now state that telemetry is written locally under:

```text
.runsentry/runs/<run_id>/
```

and that each run writes:

- `telemetry.jsonl`;
- `summary.json`.

The docs explicitly state that stdout/stderr content is not stored, only activity
counters/facts. They also state that command argv and local paths are stored as factual
launch/run data, so users should avoid putting secrets in command arguments.

The docs state that RunSentry does not upload telemetry or contact a service.

## Health wording findings

The README and public-alpha notes now describe the P0 health states as:

- `STARTING`;
- `HEALTHY`;
- `QUIET`;
- `SUSPECTED_STALL`;
- `FAILED`;
- `COMPLETE`.

The wording explicitly says:

- `SUSPECTED_STALL` is conservative suspicion, not proof;
- silence alone is not enough to declare a stall;
- absence of a watch path is not stall evidence;
- unavailable process/output/watch facts reduce confidence rather than increasing
  suspicion;
- `SUSPECTED_STALL` can recover if activity resumes;
- RunSentry never automatically kills or recovers workloads in P0.

## Limitations documented

The public-facing documentation now records these P0 limitations:

- local machine only;
- macOS and Linux target;
- no Windows compatibility promise;
- no web dashboard;
- no SaaS or remote monitoring;
- no notifications;
- no database;
- no workflow orchestration;
- no AI/LLM health judgment;
- no automatic kill or recovery;
- no OOM prediction;
- no disk exhaustion prediction;
- no generic job-completion ETA;
- process/resource facts may be partial due to OS permissions;
- conservative health rules may miss real stalls.

## Issue template decision

Minimal GitHub issue templates were added:

- bug report;
- feature request.

The bug report template asks for OS, Python version, RunSentry version/commit, command,
expected behavior, actual behavior, and a sanitized `summary.json` excerpt. The feature
request template includes a P0 scope check to discourage requests that would turn
RunSentry into a dashboard, SaaS, orchestration, notification, or automatic intervention
system.

No governance, CLA, release, or project-management machinery was added.

## CI status

The existing GitHub Actions workflow is appropriate for P0 public-alpha readiness:

- Ubuntu on Python 3.10, 3.11, and 3.12;
- macOS on Python 3.12;
- install with `.[test]`;
- run `pytest`.

No release automation, PyPI publishing, Docker build, or coverage service was added.

CI was not remotely queried during this task. Local validation was run with Python
3.12.14.

## Examples checked

The README includes small examples only:

```bash
runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
```

```bash
runsentry run --name io-demo --watch out.log -- python3 job.py
```

```bash
runsentry run --name shell-demo -- bash -lc 'python3 job.py | tee output.log'
```

A local smoke run was performed against the safe sleep example using the repository
virtual environment and an ignored `.runsentry/` output directory.

## Changes made

Created:

- `docs/public-alpha.md`;
- `.github/ISSUE_TEMPLATE/bug_report.md`;
- `.github/ISSUE_TEMPLATE/feature_request.md`;
- `docs/RS-P0-011-public-alpha-readiness-audit.md`.

Modified:

- `README.md`;
- `src/runsentry/cli.py`;
- `pyproject.toml`.

Runtime behavior was not changed. The only source-code change was CLI help text.

## Validation result

Validation commands run:

```bash
.venv/bin/python -m py_compile src/runsentry/*.py
.venv/bin/runsentry --help
.venv/bin/runsentry run --help
.venv/bin/runsentry run --output-dir .runsentry/public-alpha-smoke --name demo -- .venv/bin/python -c "import time; time.sleep(0.1)"
.venv/bin/python -m pytest -q
```

Observed results:

- Python version: 3.12.14;
- CLI help commands succeeded;
- safe example smoke command exited `0`;
- safe example run directory:
  `.runsentry/public-alpha-smoke/runs/20260907T203504Z-a42bedb533df/`;
- safe example final health state: `COMPLETE`;
- safe example telemetry line count: 3;
- safe example forbidden prediction/intervention fields were absent;
- full pytest result: 106 passed, 3 skipped;
- generated `.runsentry/` artifacts remained ignored.

## Remaining blockers

No blockers for conservative GitHub public alpha were found.

Remaining non-blocking notes:

- CI status should be checked on GitHub after pushing the branch/commit.
- Public issue triage should treat `SUSPECTED_STALL` reports as conservative heuristic
  feedback, not proof of a defect.
- Future public docs can add more examples after real user feedback, but the current
  examples are intentionally minimal.

## Final recommendation

`READY_FOR_PUBLIC_ALPHA`
