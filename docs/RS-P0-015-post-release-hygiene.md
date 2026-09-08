# RS-P0-015 Post-Release Hygiene

## Objective

Polish the public GitHub alpha for discoverability, trust, and safe early-user
feedback after `v0.1.0-alpha.1`.

No runtime features, health logic, telemetry schema changes, release tags, PyPI
publishing, dashboards, notifications, prediction features, automatic kill, or recovery
work were added.

## README review

README status: ready.

The README answers the first-time visitor questions:

- what RunSentry is;
- who it is for;
- what problem it solves;
- public alpha status;
- current P0 capabilities;
- install from source;
- quick-start command;
- `--` boundary behavior;
- `--watch` examples;
- where telemetry goes;
- health state meanings;
- what RunSentry does not do;
- privacy warning;
- how to report useful issues.

Small wording polish added a concise audience statement and clarified that generated
`.runsentry/` artifacts should normally stay out of commits.

## Issue template review

Issue template status: ready.

The bug report template asks for:

- OS;
- Python version;
- RunSentry version/tag or commit;
- command used;
- expected behavior;
- actual behavior;
- sanitized `summary.json` excerpt;
- whether stdout/stderr contained secrets or private data;
- whether the workload can be reproduced with a small synthetic script.

The feature request template remains intentionally short and includes a P0 scope check.

## Topic recommendations

Recommended GitHub topics:

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

Manual GitHub step:

1. Open repository settings/sidebar metadata on GitHub.
2. Set the repository description to:
   `Lightweight local health observer for long-running commands and Python jobs.`
3. Add the topics above.

No CLI topic-setting command was run in this task.

## Public alpha feedback loop

Early-user signals to watch:

- non-owner clone/install;
- stars;
- issues;
- repeat users;
- feature requests;
- requests for notification, remote, or multi-machine features;
- willingness-to-pay or organizational-adoption signals.

This does not imply payment, SaaS, hosted telemetry, or commercial functionality in P0.

## Privacy wording review

Privacy/security wording status: ready.

Public docs state:

- telemetry is local;
- stdout/stderr content is not stored;
- stdout/stderr counters are stored;
- command argv and local paths are stored;
- users should avoid passing secrets in argv;
- generated `.runsentry/` artifacts should not be committed;
- no network upload occurs.

The bug template also reminds users not to paste stdout/stderr content containing
secrets or private data.

## Release page review

The release page itself was not modified. The release notes in
`docs/RS-P0-014-alpha-release-notes.md` are consistent with README positioning:

- source-install alpha;
- local observer scope;
- command wrapping after `--`;
- stdout/stderr activity observation without content storage;
- process/resource facts;
- watched path/disk facts;
- local telemetry and summary;
- conservative health states;
- explicit no-production-supervisor, no-prediction, no-auto-intervention limitations.

## Clean clone/install smoke

Clean clone/install smoke result: passed.

Temporary clone path:

`/private/tmp/runsentry-clean-clone-015.nUEnHK/runsentry`

Observed results:

- clone URL: `https://github.com/zhangchao102282-dot/runsentry.git`;
- Python: 3.12;
- editable install with `.[test]`: passed;
- clean-clone pytest: 109 passed;
- `runsentry --help`: passed;
- demo smoke command exit code: 0;
- demo final health state: `COMPLETE`;
- demo summary path:
  `.runsentry/clean-clone-smoke/runs/20260908T105448Z-d37f24b790a3/summary.json`;
- forbidden prediction/intervention fields absent from demo summary.

The clean-clone command required network access for GitHub and PyPI. Generated clone
artifacts were kept under `/private/tmp` and were not committed.

Planned command shape:

```bash
git clone https://github.com/zhangchao102282-dot/runsentry.git
cd runsentry
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest -q
.venv/bin/runsentry --help
.venv/bin/runsentry run --output-dir .runsentry/clean-clone-smoke --name demo -- .venv/bin/python -c "import time; time.sleep(0.1)"
```

## Validation result

Validation result: passed.

Observed local results:

- local Python: 3.12.14;
- `.venv/bin/python -m pytest -q`: 106 passed, 3 skipped;
- `.venv/bin/runsentry --help`: passed;
- `.venv/bin/runsentry run --help`: passed.

Required local checks:

```bash
.venv/bin/python -m pytest -q
.venv/bin/runsentry --help
.venv/bin/runsentry run --help
```

## Remaining public-alpha notes

- Keep public claims conservative.
- Treat `SUSPECTED_STALL` as heuristic feedback, not certainty.
- Use sanitized `summary.json` excerpts for debugging public issues.
- Do not expand into notifications, remote monitoring, hosted dashboards, prediction
  features, or intervention behavior without a separate product decision.

## Demand validation readiness

`READY_FOR_DEMAND_VALIDATION`
