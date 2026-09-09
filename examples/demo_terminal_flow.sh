#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
RUNSENTRY_BIN="${RUNSENTRY:-runsentry}"
TMP_ROOT="${RUNSENTRY_DEMO_TMP:-/tmp}"
WATCH_PATH="${TMP_ROOT%/}/rs-demo.txt"
ARTIFACT_DIR="${TMP_ROOT%/}/rs-demo"

if [[ "${PYTHON:-}" == "" && -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

if [[ "${RUNSENTRY:-}" == "" ]] && ! command -v "$RUNSENTRY_BIN" >/dev/null 2>&1 && [[ -x ".venv/bin/runsentry" ]]; then
  RUNSENTRY_BIN=".venv/bin/runsentry"
fi

"$PYTHON_BIN" - "$WATCH_PATH" "$ARTIFACT_DIR" <<'PY'
import shutil
import sys
from pathlib import Path

watch_path = Path(sys.argv[1])
artifact_dir = Path(sys.argv[2])
watch_path.unlink(missing_ok=True)
shutil.rmtree(artifact_dir, ignore_errors=True)
PY

printf '$ runsentry --version\n'
"$RUNSENTRY_BIN" --version
printf '\n'

printf '$ runsentry run --name demo --watch /tmp/rs-demo.txt --output-dir /tmp/rs-demo -- python examples/demo_long_job.py --output /tmp/rs-demo.txt\n'
"$RUNSENTRY_BIN" run \
  --name demo \
  --watch "$WATCH_PATH" \
  --output-dir "$ARTIFACT_DIR" \
  -- "$PYTHON_BIN" examples/demo_long_job.py --output "$WATCH_PATH"
printf '\n'

SUMMARY_PATH="$(find "$ARTIFACT_DIR/runs" -name summary.json | sort | tail -n 1)"
"$PYTHON_BIN" - "$SUMMARY_PATH" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
telemetry_path = Path(summary["telemetry_file_path"])

print("RunSentry artifacts:")
print(f"  telemetry.jsonl: {telemetry_path}")
print(f"  summary.json: {summary_path}")
print(f"  final_health_state: {summary['final_health_state']}")
print(f"  exit_code: {summary['exit_code']}")
PY
