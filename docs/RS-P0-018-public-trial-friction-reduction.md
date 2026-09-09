# RS-P0-018 Public Trial Friction Reduction

Date: 2026-09-09

## Diagnosis

The public alpha has a working local observer, green CI, a published GitHub release, and
clean source-install smoke results. The current bottleneck is first-trial friction:
visitors need to understand the value quickly, see a low-risk demo command, and have a
clear path toward eventual `pip install runsentry` usage without being told that PyPI is
available before publication.

No runtime monitoring capability was added for this task.

## PyPI Readiness

Status: `PYPI_READY_WITH_CHANGES`

Changes made:

- Updated package version metadata from `0.0.1.dev0` to `0.1.0a1`, matching the current
  public alpha line in valid PEP 440 form.
- Updated the import/version test to assert `0.1.0a1`.
- Updated license metadata to SPDX-style `license = "MIT"` and raised the setuptools
  build requirement to `setuptools>=77` to avoid current license metadata deprecation
  warnings.

Audit result:

- Package name: `runsentry`
- Source layout: `src/runsentry`
- Console script: `runsentry = "runsentry.cli:main"`
- Python requirement: `>=3.10`
- Runtime dependency: `psutil>=5.9`
- Build backend: `setuptools.build_meta`
- License file: `LICENSE`, MIT
- README long description: Markdown README is suitable for packaging; no local render
  failure was observed during build metadata generation.

Package-name availability:

- `https://pypi.org/project/runsentry/` returned 404 on 2026-09-09.
- This confirms no visible PyPI project page at check time.
- It does not reserve the name or remove the normal publication race; final ownership is
  only established by manual upload through the PyPI account.

## Build Result

Command:

```bash
.venv/bin/python -m build --outdir /tmp/runsentry-build-rs-p0-018-final
```

Result: PASS

Artifacts:

- `/tmp/runsentry-build-rs-p0-018-final/runsentry-0.1.0a1.tar.gz`
- `/tmp/runsentry-build-rs-p0-018-final/runsentry-0.1.0a1-py3-none-any.whl`

## Fresh Wheel Install Result

Commands:

```bash
.venv/bin/python -m venv /tmp/runsentry-wheel-venv-rs-p0-018-final
/tmp/runsentry-wheel-venv-rs-p0-018-final/bin/python -m pip install \
  /tmp/runsentry-build-rs-p0-018-final/runsentry-0.1.0a1-py3-none-any.whl
/tmp/runsentry-wheel-venv-rs-p0-018-final/bin/runsentry --help
/tmp/runsentry-wheel-venv-rs-p0-018-final/bin/runsentry run --help
```

Result: PASS

Note: the first install attempt failed inside the restricted sandbox because `psutil`
needed PyPI network resolution. The same wheel install passed after approved network
access.

## Demo Design

Created:

- `examples/demo_long_job.py`

The demo:

- runs for about 12 seconds;
- prints deterministic stdout progress lines;
- prints one stderr line, proving stderr passthrough is preserved;
- writes and appends to `/tmp/runsentry-demo-output.txt`;
- uses modest CPU and memory;
- exits with status 0;
- requires no network, external service, Sentinel path, or user-specific path.

Recommended visual-demo command:

```bash
runsentry run \
  --name demo \
  --watch /tmp/runsentry-demo-output.txt \
  -- python examples/demo_long_job.py
```

For a recording later, use any local terminal recorder already available on the machine.
External tools such as asciinema, VHS, terminalizer, or ffmpeg may help, but none are
required by RunSentry and none were added as project dependencies.

## Demo Validation

Wheel-installed command:

```bash
/tmp/runsentry-wheel-venv-rs-p0-018-final/bin/runsentry run \
  --name demo \
  --watch /tmp/runsentry-demo-output.txt \
  --output-dir /tmp/runsentry-wheel-demo-rs-p0-018-final \
  -- /tmp/runsentry-wheel-venv-rs-p0-018-final/bin/python examples/demo_long_job.py
```

Result: PASS

Observed:

- child stdout was printed;
- child stderr was printed;
- `telemetry.jsonl` existed;
- `summary.json` existed;
- telemetry JSONL had 15 lines;
- final health was `COMPLETE`;
- exit code was 0;
- stdout byte count was 258;
- stderr byte count was 30;
- watched file size was 169 bytes;
- forbidden prediction/intervention fields were not introduced.

Artifact paths:

- `/tmp/runsentry-wheel-demo-rs-p0-018-final/runs/20260909T140326Z-c81375b6c99a/telemetry.jsonl`
- `/tmp/runsentry-wheel-demo-rs-p0-018-final/runs/20260909T140326Z-c81375b6c99a/summary.json`

## README Changes

The README first screen now opens with:

- "A lightweight local observer for long-running commands."
- one wrapper command;
- a short factual list of recorded evidence;
- explicit "No daemon. No cloud. No automatic killing.";
- a demo command using the new example script;
- source installation as the current supported path;
- planned PyPI installation described as future only.

The README does not tell users to run `pip install runsentry` yet.

## Validation

Commands and results:

- `.venv/bin/python -m pytest -q`: PASS, 106 passed, 3 skipped.
- `.venv/bin/runsentry --help`: PASS.
- `.venv/bin/runsentry run --help`: PASS.
- `.venv/bin/python -m build --outdir /tmp/runsentry-build-rs-p0-018-final`: PASS.
- Fresh temporary venv wheel install: PASS after approved dependency network access.
- Wheel-installed `runsentry --help`: PASS.
- Wheel-installed `runsentry run --help`: PASS.
- Wheel-installed demo run: PASS.

## Remaining Manual Steps Before PyPI Publication

1. Confirm PyPI account ownership, 2FA, and trusted publishing or API token setup.
2. Re-check `https://pypi.org/project/runsentry/` immediately before upload.
3. Build from a clean checkout at the intended release commit.
4. Upload to TestPyPI if desired.
5. Install from TestPyPI in a fresh environment if used.
6. Upload to PyPI manually.
7. Verify `pip install runsentry` and `runsentry --help` from a fresh environment.
8. Update README installation wording only after PyPI publication succeeds.

## Visual Recording Status

A visual recording is still needed for distribution. The deterministic terminal demo is
ready to record, but no GIF/video was produced in this task.

## Recommendation

Next step: manually publish the verified package to PyPI when ready, then update the
README installation section from "future/planned" to actual PyPI install instructions
and record the short terminal demo.
