import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-seconds", type=float, default=60.0)
    parser.add_argument("--exit-code", type=int, default=7)
    args = parser.parse_args()

    print("crash_after_60s: start", flush=True)
    time.sleep(args.after_seconds)
    print("crash_after_60s: failing", file=sys.stderr, flush=True)
    return args.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
