# RS-P0-020D Alpha.2 Release Notes

Version: `0.1.0a2`

GitHub tag/release plan: `v0.1.0-alpha.2`

## Public Summary

RunSentry 0.1.0a2 fixes latency when forwarding small flushed stdout/stderr writes from
long-running child processes. Progress output can now appear promptly instead of being
delayed until a large pipe read fills or the child exits.

## Purpose

Prepare the alpha.2 release for the output tee latency correctness repair from
RS-P0-020C. PyPI already contains `runsentry==0.1.0a1`, so the repair must be released as
a new alpha version rather than overwriting alpha.1.

## Root Cause

RunSentry previously used:

```python
self.source.read(READ_CHUNK_SIZE)
```

on a buffered `subprocess.PIPE` file object. With `READ_CHUNK_SIZE = 64 KiB`, small
flushed child writes could remain buffered until EOF or until a large read filled.

## Fix

For real pipe file descriptors, `StreamDrainer` now uses:

```python
os.read(fd, READ_CHUNK_SIZE)
```

The file-like-object fallback is preserved for objects without a usable file descriptor.

## Preserved Semantics

- Byte-preserving forwarding remains unchanged.
- stdout and stderr remain separate streams.
- Cross-stream ordering is not guaranteed.
- No PTY support was added.
- No line parsing or decode/re-encode path was added.
- No stdout/stderr content retention was added.
- No supervisor, auto-kill, restart, or recovery behavior was added.

## Regression Coverage

Added `test_small_flushed_stdout_is_forwarded_before_child_exit`.

The test proves a small flushed stdout line is forwarded before the child exits and while
the child is still running.

## Validation

Commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/runsentry --help
.venv/bin/runsentry run --help
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
bash examples/demo_terminal_flow.sh
```

Results:

- `.venv/bin/runsentry --version`: PASS, `runsentry 0.1.0a2`.
- Full test suite: PASS, `107 passed, 3 skipped`.
- Output latency regression: PASS.
- SIGINT tests: PASS.
- Byte-preserving tests: PASS.
- stderr passthrough tests: PASS.
- Build: PASS, produced `dist/runsentry-0.1.0a2.tar.gz` and
  `dist/runsentry-0.1.0a2-py3-none-any.whl`.
- Twine check: PASS for both dist artifacts.
- Fresh wheel install: PASS in `/tmp/runsentry-alpha2-wheel-venv`.
- Wheel-installed `runsentry --version`: PASS, `runsentry 0.1.0a2`.
- Wheel-installed `runsentry --help`: PASS.
- Wheel-installed `runsentry run --help`: PASS.
- Wheel demo: PASS, final health `COMPLETE`, exit code 0.
- Wheel demo timing: PASS, step deltas approximately `2.00,2.00,2.00,2.00,2.00`
  seconds.
- Wheel demo telemetry:
  `/tmp/rs-demo/runs/20260909T212059Z-729accbdb72b/telemetry.jsonl`.
- Wheel demo summary:
  `/tmp/rs-demo/runs/20260909T212059Z-729accbdb72b/summary.json`.

Do not publish to PyPI, create a GitHub tag, or create a GitHub Release as part of this
preparation task. Those are manual release actions after validation.
