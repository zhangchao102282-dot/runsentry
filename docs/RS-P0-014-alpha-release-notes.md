# RunSentry v0.1.0-alpha.1 Release Notes

## Version

`v0.1.0-alpha.1`

## Repository

https://github.com/zhangchao102282-dot/runsentry

## Release status

Public alpha.

This is the first conservative public alpha of RunSentry. It is intended for early
users who want a lightweight local observer around long-running commands and Python
jobs. It is not a production supervisor.

## Summary

RunSentry v0.1.0-alpha.1 is the first public alpha of a lightweight local observer for
long-running commands and Python jobs. It wraps a command after an explicit `--`
boundary, tees stdout/stderr, records process/resource facts, watched path/disk facts,
local JSONL telemetry, `summary.json`, and conservative health states.

## Supported runtime

- Python: `>=3.10`
- OS target: macOS and Linux
- Runtime dependency: `psutil`

No Windows compatibility promise is made for this alpha.

## Installation from source

```bash
git clone https://github.com/zhangchao102282-dot/runsentry.git
cd runsentry
python -m pip install -e .
```

For local development validation:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

RunSentry is not published to PyPI for this alpha.

## Quick start

Observe a simple command:

```bash
runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
```

Observe a job and watch an output path:

```bash
runsentry run --name io-demo --watch out.log -- python3 job.py
```

RunSentry does not invoke a shell. If shell behavior is needed, launch a shell
explicitly:

```bash
runsentry run --name shell-demo -- bash -lc 'python3 job.py | tee output.log'
```

## Current P0 capabilities

This alpha includes:

- direct command wrapping after an explicit `--` boundary;
- `shell=False` execution semantics;
- argv preservation for child arguments after `--`;
- stdout/stderr byte-preserving tee;
- stdout/stderr activity counters without storing output content;
- process lifecycle and resource fact snapshots;
- root process and observed descendant facts;
- watched file/directory size, mtime, file-count, replacement, and deletion facts;
- local disk usage facts for watched paths;
- local `.runsentry/runs/<run_id>/telemetry.jsonl`;
- local `.runsentry/runs/<run_id>/summary.json`;
- conservative health states:
  - `STARTING`
  - `HEALTHY`
  - `QUIET`
  - `SUSPECTED_STALL`
  - `FAILED`
  - `COMPLETE`
- synthetic scenario validation;
- local dogfood validation.

## Output artifacts

By default, each run writes local artifacts under:

```text
.runsentry/
  runs/
    <run_id>/
      telemetry.jsonl
      summary.json
```

Use `--output-dir` to place artifacts elsewhere.

## Privacy and security notes

- Telemetry is local.
- RunSentry does not upload telemetry.
- RunSentry does not contact a remote service.
- stdout/stderr content is not stored in telemetry or summary files.
- stdout/stderr byte and chunk counters are stored.
- command argv is stored and may contain sensitive values.
- local paths are stored and may reveal private project structure.
- generated `.runsentry/` artifacts should not be committed.
- sanitize `summary.json` before sharing it publicly.

## Explicit limitations

RunSentry v0.1.0-alpha.1 does not provide:

- production-supervisor guarantees;
- guaranteed stuck-process detection;
- OOM prediction;
- disk exhaustion prediction;
- generic job-completion ETA;
- automatic kill;
- automatic recovery;
- notifications;
- dashboard;
- SaaS or remote monitoring;
- database-backed telemetry;
- workflow orchestration;
- Kubernetes integration;
- AI/LLM health judgment.

`SUSPECTED_STALL` means conservative suspicion, not proof. Silence alone is not enough
to declare a stall. Missing watched paths, absent watch configuration, and unavailable
metrics reduce confidence rather than increasing suspicion.

Process/resource visibility may be partial due to operating-system permissions and
normal process-race behavior.

## Validation summary

Pre-release validation for this tag:

- latest commit before release-note commit: `1494188 RS-P0-013A fix CI test helper imports`;
- local Python: 3.12.14;
- local pytest: 106 passed, 3 skipped;
- `runsentry --help`: passed;
- `runsentry run --help`: passed;
- README quick-start smoke command: exit 0, final health `COMPLETE`;
- smoke telemetry lines: 3;
- forbidden prediction/intervention fields absent from smoke summary;
- GitHub Actions status before RS-P0-014: reported passing by the project owner;
- README and `docs/public-alpha.md` inspected for conservative release wording.

## Known notes

- This alpha is source-install only.
- CI should be rechecked after pushing the release-notes commit and tag.
- Public feedback should focus on launch behavior, argv preservation, stdout/stderr
  forwarding, telemetry usefulness, watched-path facts, and false/confusing health states.
- Requests for hosted, remote, multi-machine, notification, or intervention features
  should be evaluated separately and not treated as P0 scope.

## Manual tag commands

After committing these release notes and confirming validation:

```bash
git tag -a v0.1.0-alpha.1 -m "RunSentry v0.1.0-alpha.1"
git push origin v0.1.0-alpha.1
```

Do not create the GitHub release page until after the tag is pushed and CI status is
checked.
