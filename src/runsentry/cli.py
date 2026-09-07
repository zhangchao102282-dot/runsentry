from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .execution import EXIT_USAGE, LaunchError, RunSpec, run_command
from .observation import DEFAULT_RESOURCE_SAMPLE_INTERVAL_S
from .version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runsentry",
        description="Local health observer for long-running commands.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command_name")
    run_parser = subparsers.add_parser(
        "run",
        help="launch a command and tee stdout/stderr",
        description="Launch a command directly and observe stdout/stderr bytes.",
    )
    run_parser.add_argument("--name", default=None)
    run_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_RESOURCE_SAMPLE_INTERVAL_S,
        help="resource sampling interval in seconds",
    )
    run_parser.add_argument(
        "run_args",
        nargs=argparse.REMAINDER,
        help="RunSentry options, then --, then the child command argv",
    )
    run_parser.set_defaults(func=_run)
    return parser


def _parse_run_args(
    name: str | None,
    interval: float,
    run_args: Sequence[str],
) -> RunSpec:
    if interval < 1.0 or interval > 60.0:
        raise LaunchError("runsentry run --interval must be between 1.0 and 60.0.", EXIT_USAGE)

    if "--" not in run_args:
        raise LaunchError(
            "runsentry run requires an explicit -- before the command.",
            EXIT_USAGE,
        )

    boundary_index = list(run_args).index("--")
    option_args = list(run_args[:boundary_index])
    command_argv = list(run_args[boundary_index + 1 :])
    if not command_argv:
        raise LaunchError("runsentry run requires a command after --.", EXIT_USAGE)

    if option_args:
        raise LaunchError(
            f"unexpected argument before --: {option_args[0]}",
            EXIT_USAGE,
        )

    return RunSpec(name=name, argv=command_argv, sample_interval_s=interval)


def _run(args: argparse.Namespace) -> int:
    try:
        run_spec = _parse_run_args(args.name, args.interval, args.run_args)
        return run_command(run_spec)
    except LaunchError as exc:
        print(f"runsentry: {exc}", file=sys.stderr)
        return exc.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))
