from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic long-running demo job for RunSentry.",
    )
    parser.add_argument(
        "--output",
        default="/tmp/runsentry-demo-output.txt",
        help="file to update while the demo runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("RunSentry demo output\n", encoding="utf-8")

    print("demo: starting deterministic long job", flush=True)
    print(f"demo: writing watched file at {output_path}", flush=True)
    print("demo: stderr is preserved too", file=sys.stderr, flush=True)

    for step in range(1, 7):
        checksum = sum(index * step for index in range(2500))
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(f"step={step} checksum={checksum}\n")
            handle.flush()
        print(f"demo: step {step}/6 complete", flush=True)
        time.sleep(2)

    print("demo: complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
