# RunSentry

RunSentry is a lightweight local health observer for long-running commands and Python jobs.

The P0 target CLI is:

```text
runsentry run --name JOB_NAME --watch PATH -- python3 job.py
```

Current RS-P0-005 behavior implements the command boundary, safe launch primitive, stdout/stderr byte observation, and internal factual process/resource snapshots:

```text
runsentry run [--name JOB_NAME] -- COMMAND [ARG ...]
```

It launches the command directly with `shell=False`, inherits stdin, forwards stdout/stderr as raw bytes through separate pipes, periodically samples factual process/resource data, waits for completion, and propagates the child exit result. Telemetry, health states, watched paths, and interpretation logic are not implemented yet.

Core principles:

- observer-first
- local-first
- non-invasive
- conservative health judgment
- does not automatically kill workloads

P0 is intentionally small. It does not include a web dashboard, SaaS service, user accounts, billing, Redis, Kubernetes, Docker requirements, task queues, AI/LLM health judgment, automatic kill, or automatic recovery.

## Development Status

This repository is currently at scaffold stage. The implementation contract is defined in:

- `docs/RS-P0-001-specification.md`
- `docs/RS-P0-001A-audit.md`
- `docs/RS-P0-002-scaffold-record.md`
- `docs/RS-P0-003-execution-record.md`
- `docs/RS-P0-004-output-observation-record.md`
- `docs/RS-P0-004A-repository-isolation-record.md`
- `docs/RS-P0-005-process-resource-record.md`

## License

MIT.
