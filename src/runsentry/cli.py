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
        description="Local conservative health observer for one long-running command.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command_name")
    run_parser = subparsers.add_parser(
        "run",
        help="observe a command after an explicit -- boundary",
        description=(
            "Launch COMMAND directly with shell=False, tee stdout/stderr, "
            "observe local facts, and write .runsentry telemetry."
        ),
    )
    run_parser.add_argument("--name", default=None, help="optional human-readable run name")
    run_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_RESOURCE_SAMPLE_INTERVAL_S,
        help="resource/watch/telemetry sampling interval in seconds",
    )
    run_parser.add_argument(
        "--watch",
        action="append",
        default=[],
        help="path to observe for factual size/mtime/disk data",
    )
    run_parser.add_argument(
        "--output-dir",
        default=None,
        help="directory for RunSentry telemetry artifacts",
    )
    run_parser.add_argument(
        "run_args",
        nargs=argparse.REMAINDER,
        help="must contain -- followed by COMMAND [ARG ...]; all arguments after -- belong to the child",
    )
    run_parser.set_defaults(func=_run)
    return parser


def _parse_run_args(
    name: str | None,
    interval: float,
    watches: Sequence[str],
    output_dir: str | None,
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

    watch_paths = list(watches) + _parse_watch_options(option_args)

    return RunSpec(
        name=name,
        argv=command_argv,
        sample_interval_s=interval,
        watch_paths=watch_paths,
        output_dir=output_dir,
    )


def _parse_watch_options(option_args: list[str]) -> list[str]:
    watch_paths: list[str] = []
    index = 0
    while index < len(option_args):
        arg = option_args[index]
        if arg != "--watch":
            raise LaunchError(f"unexpected argument before --: {arg}", EXIT_USAGE)
        index += 1
        if index >= len(option_args):
            raise LaunchError("runsentry run --watch requires a path.", EXIT_USAGE)
        watch_paths.append(option_args[index])
        index += 1
    return watch_paths


def _run(args: argparse.Namespace) -> int:
    try:
        run_spec = _parse_run_args(
            args.name,
            args.interval,
            args.watch,
            args.output_dir,
            args.run_args,
        )
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
