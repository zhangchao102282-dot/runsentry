# RS-P0-003 Execution Record

## Objective

Implement the first real RunSentry execution primitive: parse an explicit command boundary, preserve child argv, launch the command directly, wait for completion, handle Ctrl-C conservatively, and propagate deterministic exit results.

## Execution Model

`runsentry run [--name JOB_NAME] -- COMMAND [ARG ...]` launches exactly one root child process and waits for it to exit. RS-P0-003 records launch information internally as `RunSpec` and `LaunchInfo`: optional name, argv, PID, monotonic start time, and return code shape. It does not persist this information yet.

No process monitoring is implemented. RS-P0-003 does not inspect descendants, sample resources, write telemetry, track health, observe output activity, or watch files.

## Argv Boundary Semantics

- The child command must appear after an explicit `--`.
- Missing `--` is a usage error.
- Empty command after `--` is a usage error.
- RunSentry options are parsed only before `--`.
- Child arguments after `--` are passed through unchanged, including arguments that look like RunSentry options.
- Shell metacharacters after `--`, such as `*`, `$HOME`, `;`, and `|`, are ordinary argv strings unless the user explicitly chooses a shell as the command.
- `--name` is optional in RS-P0-003 to support the task examples. Later monitoring tasks can tighten this toward the frozen full P0 CLI contract if needed.

## shell=False Guarantee

The implementation uses:

```text
subprocess.Popen(argv, shell=False, stdin=None, stdout=None, stderr=None)
```

RunSentry does not join argv, parse quoting, invoke `/bin/sh`, call `os.system`, or set `shell=True`.

`runsentry run -- bash -lc 'echo hello'` is allowed because the user explicitly made `bash` the child command. In that case, shell semantics belong to the user's child process, not RunSentry.

## Stdio Inheritance Semantics

RS-P0-003 intentionally inherits stdin, stdout, and stderr. It does not create stdout/stderr pipes and does not observe output activity. This makes the child behave as close as practical to a directly launched terminal process at this stage.

Pipe and tee behavior is deferred to RS-P0-004.

## Exit-Code Mapping

- CLI usage error: `2`
- Command not found: `127`
- Permission denied while launching command: `126`
- Other launch failure: `1`
- Child normal exit `N`: RunSentry exits `N`
- Child terminated by signal `S`: RunSentry exits `128 + S`
- Ctrl-C while waiting: normally exits `130`

RunSentry does not silently convert child failures to `1`.

## Ctrl-C and Signal Behavior

RS-P0-003 does not create a new process group and does not manually forward SIGINT on `KeyboardInterrupt`. On macOS and Linux terminals, RunSentry and its child normally share the foreground process group, so terminal Ctrl-C is delivered by the terminal driver to both processes. Manual forwarding in that path would risk delivering SIGINT twice.

When RunSentry receives `KeyboardInterrupt`, it checks whether the child has exited. If not, it waits up to five seconds for the child to finish after the same interrupt. If the child remains alive, RunSentry exits `130` with a diagnostic and does not kill the child.

This is intentionally not a general signal supervisor. Process-group creation and explicit signal forwarding belong to later supervision/monitoring work.

## Platform Assumptions

The implementation targets macOS and Linux. It assumes POSIX-like terminal foreground process-group behavior for interactive Ctrl-C. Windows is not a P0 compatibility target.

## RunSentry Failure Semantics

If RunSentry terminates unexpectedly after launching the child, RS-P0-003 provides no reattach, daemonization protection, or recovery. Because stdio is inherited rather than piped, an unexpected RunSentry crash should not intentionally close child stdout/stderr pipes created by RunSentry. Whether the child continues depends on ordinary parent/terminal/session semantics.

## Tests Added

- CLI help still returns success.
- `python -m runsentry --help` still returns success.
- Child stdout marker is visible through inherited stdout.
- Child exit `0` propagates as `0`.
- Child exit `7` propagates as `7`.
- Missing command returns `127`.
- Missing `--` returns usage error `2`.
- Empty command after `--` returns usage error `2`.
- `--name` is parsed as a RunSentry option and does not leak to child argv.
- Child `--name` and `--watch` after `--` remain child argv.
- Arguments containing spaces, literal quotes, dashes, Unicode, `*`, `$HOME`, `;`, and `|` are preserved as argv and not interpreted as shell syntax.
- Bounded SIGINT integration test sends SIGINT to a test process group and expects RunSentry to return `130` without a manual-forwarding diagnostic.

## Validation Performed

- `python3 --version`: `Python 3.9.5`; below the RunSentry `>=3.10` contract.
- `python3 -m pip install -e .`: failed locally because this machine's Python 3.9 pip does not support editable pyproject installation in this scaffold.
- `python3 -m pytest`: failed locally because pytest is not installed for the available Python 3.9.5 interpreter.
- `runsentry --help`: failed locally because editable install could not complete.
- `python3 -m py_compile src/runsentry/__init__.py src/runsentry/__main__.py src/runsentry/cli.py src/runsentry/execution.py src/runsentry/version.py`: passed under Python 3.9.5 as a weaker syntax smoke check.
- `PYTHONPATH=src python3 -m runsentry --help`: passed.
- `PYTHONPATH=src python3 -m runsentry run --name smoke -- python3 -c "print('RS_P0_003_SMOKE')"`: passed and printed `RS_P0_003_SMOKE`.
- `PYTHONPATH=src python3 -m runsentry run -- python3 -c "print('NO_NAME_OK')"`: passed and printed `NO_NAME_OK`.
- `PYTHONPATH=src python3 -m runsentry run --name smoke -- python3 -c "raise SystemExit(7)"`: returned `7`.
- `PYTHONPATH=src python3 -m runsentry run -- runsentry-definitely-not-a-real-command-003`: returned `127`.
- `PYTHONPATH=src python3 -m runsentry run python3 -c "print('NO_BOUNDARY')"`: returned `2`; `NO_BOUNDARY` did not execute.
- `PYTHONPATH=src python3 -m runsentry run --`: returned `2`.
- Manual argv preservation smoke with spaces, quotes, dash-prefixed args, Unicode, `*`, `$HOME`, `;`, and `|`: passed.
- Bounded SIGINT source-tree smoke: returned `130`.

## Validation Limitations

Local validation is not P0-compliant because this iMac currently exposes only Python 3.9.5 on PATH. The project Python requirement was not weakened. Full install and pytest validation are expected from CI on Python 3.10, 3.11, and 3.12.

## Consciously Deferred Work

- psutil usage
- process-tree enumeration
- descendant lifecycle handling
- stdout/stderr pipes or activity tracking
- watched paths
- CPU, RSS, RAM, swap, and disk sampling
- telemetry and JSONL
- final summaries
- health state machine
- throughput and ETA
- notifications
- PTY support
- shell mode
- automatic kill, recovery, or timeout escalation

## Deviations From Task Specification

- No compliant local `python -m pip install -e .` or pytest run was possible because the only local Python exposed is 3.9.5 and pytest is not installed.
