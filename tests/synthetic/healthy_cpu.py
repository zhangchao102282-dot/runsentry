import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=1.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.duration_seconds
    value = 0
    print("healthy_cpu: start", flush=True)
    while time.monotonic() < deadline:
        value = (value + 1) % 1000003
    print(f"healthy_cpu: done {value}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
