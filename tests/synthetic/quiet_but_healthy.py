import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=1.0)
    args = parser.parse_args()

    time.sleep(args.duration_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
