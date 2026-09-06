# RS-P0-002 Scaffold Record

## Objective

Create the smallest maintainable standalone Python repository scaffold for RunSentry while avoiding all process-monitoring behavior.

## Files Created

- `pyproject.toml`
- `README.md`
- `LICENSE`
- `.gitignore`
- `src/runsentry/__init__.py`
- `src/runsentry/__main__.py`
- `src/runsentry/cli.py`
- `src/runsentry/version.py`
- `tests/test_import.py`
- `tests/test_cli.py`
- `.github/workflows/ci.yml`
- `docs/RS-P0-002-scaffold-record.md`

## Files Modified

- None. The frozen RS-P0-001 and RS-P0-001A documents were not rewritten.

## Dependency Decisions

- Runtime dependency: `psutil>=5.9`, declared because the frozen P0 design intends psutil as the only runtime dependency.
- Test dependency: `pytest>=7`, declared as an optional `test` extra.
- No CLI framework, lint framework, web framework, database, task queue, plugin framework, or logging framework was added.
- Ruff was not added. At scaffold scope, installability, imports, tests, and CLI smoke checks provide enough quality signal without increasing the tool surface.

## Packaging Decisions

- Used a `src/` layout.
- Used setuptools through `pyproject.toml`.
- Package name is `runsentry`.
- Python requirement is `>=3.10`.
- Development version is `0.0.1.dev0`.
- The authoritative version is the static project version in `pyproject.toml`. Runtime code reads the installed package metadata through `importlib.metadata`.
- Console entry point is `runsentry = runsentry.cli:main`.
- License is MIT.

## CLI Placeholder Semantics

- `runsentry --help` returns success.
- `python -m runsentry --help` returns success.
- `runsentry run ...` always returns `64`.
- `runsentry run ...` prints a clear RS-P0-002 not-implemented message to stderr.
- `runsentry run ...` does not launch, inspect, monitor, wrap, or otherwise interact with the supplied command.

## Validation Performed

- `python3 --version`: failed P0 interpreter requirement locally; output was `Python 3.9.5`.
- `python3 -m pip install -e .`: failed locally because the available Python is 3.9.5 and its pip is old enough that editable pyproject builds are unsupported in this environment.
- `python3 -m pytest`: failed locally because `pytest` is not installed for the available Python 3.9.5 interpreter.
- `runsentry --help`: failed locally because the console script was not installed after editable install failed.
- `python3 -m runsentry --help`: failed locally without installation because the `src/` package is not on `sys.path`.
- `PYTHONPATH=src python3 -m runsentry --help`: passed as a source-tree smoke check.
- `PYTHONPATH=src python3 -m runsentry run -- python3 -c "print('MUST_NOT_RUN')"`: returned `64`; output did not contain `MUST_NOT_RUN`.

## Test Results

- Automated pytest suite was created but not executed locally because this machine exposes only Python 3.9.5 and has no local pytest installation.
- Source files passed `python3 -m py_compile` under Python 3.9.5, which is weaker than the required Python 3.10+ validation and is recorded only as an additional syntax smoke check.
- CI is expected to run the real scaffold test suite on Python 3.10, 3.11, and 3.12 on Ubuntu, plus Python 3.12 on macOS.

## Consciously Deferred Work

- Process launching and wrapping
- psutil usage
- PID and process-tree monitoring
- stdout/stderr capture
- watched path metrics
- disk, RAM, swap, CPU metrics
- health states
- telemetry and summaries
- throughput and ETA
- notifications
- signal forwarding
- shell behavior
- PTY behavior
- automatic kill or recovery

## Deviations From Task Specification

- Required local installed validation could not be completed because this machine exposes only Python 3.9.5 on PATH and has no local pytest installation. The project itself declares Python `>=3.10`, and CI covers Python 3.10, 3.11, 3.12, and macOS.
