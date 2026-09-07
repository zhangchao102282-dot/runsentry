import argparse
import pathlib
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-seconds", type=float, default=60.0)
    parser.add_argument("--hang-seconds", type=float, default=2.0)
    parser.add_argument("--watch-file", required=True)
    args = parser.parse_args()

    watch_path = pathlib.Path(args.watch_file)
    print("hang_after_60s: active", flush=True)
    watch_path.write_text("active\n", encoding="utf-8")
    time.sleep(args.after_seconds)
    print("hang_after_60s: entering quiet hang", flush=True)
    time.sleep(args.hang_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
