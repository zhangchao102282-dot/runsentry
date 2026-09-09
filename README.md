# RunSentry

A lightweight local observer for long-running commands.

Wrap any command without modifying it:

```bash
runsentry run --name demo -- python my_script.py
```

RunSentry records:

- process/resource activity;
- stdout/stderr activity;
- watched file/directory changes;
- conservative health state;
- local JSONL telemetry;
- final `summary.json`.

No daemon.
No cloud.
No automatic killing.

It is for developers, researchers, and local AI/agent users who want factual evidence
about commands that may stay active for minutes or hours.

## Install

RunSentry targets Python 3.10+ on macOS and Linux.

```bash
pip install runsentry
```

PyPI package: <https://pypi.org/project/runsentry/>

GitHub release `v0.1.0-alpha.1` is published to PyPI as version `0.1.0a1`.

## Quick start

```bash
runsentry run --name demo -- python my_script.py
```

## Demo

The repository includes a deterministic terminal demo that runs for about 12 seconds.
It requires this repository checkout because the example script lives under
`examples/`.

```bash
runsentry run \
  --name demo \
  --watch /tmp/runsentry-demo-output.txt \
  -- python examples/demo_long_job.py
```

To record a short terminal demo later, use:

```bash
bash examples/demo_terminal_flow.sh
```

<!-- Insert recorded terminal GIF/video here after it exists. Do not commit a broken image link. -->

## Public alpha status

RunSentry is in conservative public alpha. The P0 scope is useful for local observation
and debugging, but it is not a production supervisor or a guaranteed stuck-process
detector.

## Current P0 capabilities

RunSentry P0 can:

- launch a command directly with `shell=False`;
- preserve the child command argv after an explicit `--` boundary;
- tee child stdout and stderr back to the terminal as byte streams;
- count stdout/stderr bytes and chunks without storing output content;
- observe process/resource facts with `psutil`;
- observe watched file/directory size, mtime, file count, and disk usage facts;
- write local `.runsentry/runs/<run_id>/telemetry.jsonl`;
- write local `.runsentry/runs/<run_id>/summary.json`;
- emit conservative health states:
  - `STARTING`
  - `HEALTHY`
  - `QUIET`
  - `SUSPECTED_STALL`
  - `FAILED`
  - `COMPLETE`

`SUSPECTED_STALL` is a conservative suspicion, not proof. Silence alone is not a stall.
No watch path is not stall evidence. Unavailable metrics reduce confidence.

## Source and development installation

```bash
python -m pip install -e .
```

For development tests:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

## Basic usage

Always put the command to run after the explicit `--` boundary:

```bash
runsentry run --name demo -- python3 -c "import time; time.sleep(2)"
```

Watch an output file or directory:

```bash
runsentry run --name io-demo --watch out.log -- python3 job.py
```

Use more than one watch path:

```bash
runsentry run --watch out.log --watch output_dir -- python3 job.py
```

Everything after `--` belongs to the child command unchanged:

```bash
runsentry run --name outer -- python3 job.py --watch child-value
```

RunSentry does not invoke a shell. If you need shell syntax, launch the shell explicitly:

```bash
runsentry run --name shell-demo -- bash -lc 'python3 job.py | tee output.log'
```

In that case, the shell is the observed root process and shell quoting rules are your
responsibility.

## Output artifacts

By default, each run writes:

```text
.runsentry/
  runs/
    <run_id>/
      telemetry.jsonl
      summary.json
```

Use `--output-dir` to place artifacts elsewhere:

```bash
runsentry run --output-dir /tmp/runsentry-demo -- python3 job.py
```

Telemetry is local. RunSentry does not upload data or contact a service.

RunSentry stores stdout/stderr activity counters, not stdout/stderr content. Command argv
is stored because it is part of the factual launch record, so avoid putting secrets in
command arguments.

Generated `.runsentry/` artifacts are ignored by this repository and should normally
stay out of commits.

## Health states

- `STARTING`: the run is inside the initial observation window.
- `HEALTHY`: recent positive activity was observed.
- `QUIET`: little activity is visible, but evidence is insufficient to suspect a stall.
- `SUSPECTED_STALL`: multiple independent available signals show sustained inactivity.
- `FAILED`: the wrapped root command failed to launch or exited nonzero.
- `COMPLETE`: the wrapped root command completed successfully under current P0 semantics.

Only `FAILED` and `COMPLETE` are ordinary terminal success/failure states. `SUSPECTED_STALL`
can recover if activity resumes.

## P0 limitations

RunSentry P0 is intentionally small:

- local machine only;
- macOS and Linux target;
- no Windows compatibility promise yet;
- no web dashboard;
- no SaaS or remote monitoring;
- no notifications;
- no database;
- no workflow orchestration;
- no AI/LLM health judgment;
- no automatic kill or recovery;
- no OOM prediction;
- no disk exhaustion prediction;
- no generic job-completion ETA.

Process/resource visibility may be partial due to OS permissions. The health logic is
conservative and may miss real stalls rather than creating aggressive false positives.

## More detail

See [docs/public-alpha.md](docs/public-alpha.md) for the public-alpha readiness notes.

Historical design and implementation records live in `docs/RS-P0-*.md`.

## Reporting bugs

Use the GitHub issue templates. For behavior bugs, include:

- OS and Python version;
- the `runsentry run ...` command, with secrets removed;
- expected versus actual behavior;
- a sanitized `summary.json` excerpt if useful.

Do not share command arguments or paths that contain secrets.

## Feedback wanted

If you try RunSentry on a real local command, feedback on install friction, health-state
accuracy, `summary.json` usefulness, and missing P0 facts is especially useful.

## License

MIT.
