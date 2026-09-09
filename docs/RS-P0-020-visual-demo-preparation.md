# RS-P0-020 Visual Demo Preparation

Date: 2026-09-09

RS-P0-020C update: a runtime output tee latency repair removed the need for demo-only
pipe padding. The recording flow still invokes the child demo as `python -u
examples/demo_long_job.py`, and the demo script flushes each visible progress line.

## Objective

Prepare a short, honest terminal demo that helps a first-time visitor understand
RunSentry in about 15-20 seconds without adding runtime behavior.

No runtime monitoring code, telemetry schema, health semantics, package version, PyPI
publication, GitHub tag, or GitHub release was changed.

## Demo Command

Public demo command, from a checkout of this repository after `pip install runsentry`:

```bash
runsentry run \
  --name demo \
  --watch /tmp/rs-demo.txt \
  -- python examples/demo_long_job.py
```

The example file is part of the repository, not a console-script payload. Users need a
repo checkout for this exact demo command.

## Demo Behavior

- Script: `examples/demo_long_job.py`
- Expected duration: about 12 seconds.
- Child stdout: visible deterministic progress lines.
- Child stderr: not shown in this visual demo. Existing automated tests remain the
  stderr passthrough evidence.
- Watched file: `/tmp/rs-demo.txt`, rewritten at start and appended during each step.
- Expected exit code: 0.
- Expected final health: `COMPLETE`.
- Network or external service: none.
- Sentinel or user-specific paths: none.

## Recording Command Sequence

Use the prepared command-flow script:

```bash
bash examples/demo_terminal_flow.sh
```

The script shows:

1. A quick installed-version check with `runsentry --version`.
2. The RunSentry demo command launch.
3. Original child stdout in the terminal.
4. Local artifact paths under `/tmp/rs-demo` by default.
5. A compact final summary containing `final_health_state` and `exit_code`.

It intentionally avoids dumping full JSON.

## Recording Tool Availability

Checked local commands:

- `asciinema`: not found
- `vhs`: not found
- `terminalizer`: not found
- `ffmpeg`: not found
- `magick`: not found
- `convert`: not found

No recording utility was installed and no recording dependency was added to RunSentry.

Recommended lowest-friction method: install or use an external terminal recorder outside
the project, then run `bash examples/demo_terminal_flow.sh` in a clean terminal. A screen
recorder built into the operating system is sufficient. If a scriptable terminal GIF is
preferred later, asciinema is the smallest specialized option to try first.

## Static Example

Example terminal interaction, abridged and illustrative:

```text
$ runsentry --version
runsentry 0.1.0a2

$ runsentry run --name demo --watch /tmp/rs-demo.txt --output-dir /tmp/rs-demo -- python -u examples/demo_long_job.py --output /tmp/rs-demo.txt
demo: starting deterministic long job
demo: writing watched file at /tmp/rs-demo.txt
demo: step 1/6 complete
demo: step 2/6 complete
demo: step 3/6 complete
demo: step 4/6 complete
demo: step 5/6 complete
demo: step 6/6 complete
demo: complete

RunSentry artifacts:
  telemetry.jsonl: /tmp/rs-demo/runs/<run_id>/telemetry.jsonl
  summary.json: /tmp/rs-demo/runs/<run_id>/summary.json
  final_health_state: COMPLETE
  exit_code: 0
```

This is an example transcript for planning a recording, not fabricated live output from
a published video.

## README Insertion Point

The README now includes a `## Demo` section immediately after Quick start and before
Public alpha status. It contains the demo command, notes that a repository checkout is
required, and includes a placeholder comment for a future GIF/video without a broken
image link.

## Validation Results

- `.venv/bin/python -m pytest -q`: PASS, 106 passed, 3 skipped.
- `.venv/bin/runsentry --help`: PASS.
- `.venv/bin/runsentry run --help`: PASS.
- `bash examples/demo_terminal_flow.sh`: PASS.
- Child stdout visible: PASS.
- Child stderr visible in this visual demo: not applicable.
- `telemetry.jsonl` exists: PASS.
- `summary.json` exists: PASS.
- Final health: `COMPLETE`.
- Demo exit code: 0.
- Watched file size after demo: 169 bytes.
- User-specific absolute paths introduced into public demo docs: no.
- Runtime feature changes: no.
- Health semantic changes: no.

Validated artifact paths:

- `/tmp/rs-demo/runs/20260909T211105Z-d835f9d7a0c3/telemetry.jsonl`
- `/tmp/rs-demo/runs/20260909T211105Z-d835f9d7a0c3/summary.json`

## Remaining Manual Recording Steps

1. Use a fresh terminal at a width that keeps lines readable.
2. Confirm `pip install runsentry` has already been performed in the active environment.
3. Run `bash examples/demo_terminal_flow.sh`.
4. Record the terminal using an external recorder.
5. Trim to roughly 15-25 seconds.
6. Export the GIF/video asset.
7. Add the asset to the repository or release assets.
8. Replace the README placeholder comment with a working image/video link.

## Readiness

The project is ready to record immediately.
