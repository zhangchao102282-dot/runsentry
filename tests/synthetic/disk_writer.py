import argparse
import pathlib
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--files", type=int, default=3)
    parser.add_argument("--bytes-per-file", type=int, default=128)
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = b"x" * args.bytes_per_file
    for index in range(args.files):
        path = output_dir / f"chunk-{index}.bin"
        path.write_bytes(payload)
        print(f"disk_writer: wrote {path.name}", flush=True)
        time.sleep(args.delay_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
