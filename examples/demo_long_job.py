from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PIPE_FLUSH_PADDING_BYTES = 64 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic long-running demo job for RunSentry.",
    )
    parser.add_argument(
        "--output",
        default="/tmp/rs-demo.txt",
        help="file to update while the demo runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("RunSentry demo output\n", encoding="utf-8")

    print_progress("demo: starting deterministic long job")
    print_progress(f"demo: writing watched file at {output_path}")

    for step in range(1, 7):
        checksum = sum(index * step for index in range(2500))
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(f"step={step} checksum={checksum}\n")
            handle.flush()
        print_progress(f"demo: step {step}/6 complete")
        time.sleep(2)

    print_progress("demo: complete")
    return 0


def print_progress(message: str) -> None:
    print(message, flush=True)
    if not sys.stdout.isatty():
        # Demo-only: RunSentry P0 reads pipe output in large chunks, so nudge the
        # existing reader without adding visible terminal text.
        os.write(sys.stdout.fileno(), b"\0" * PIPE_FLUSH_PADDING_BYTES)
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
