import argparse
import pathlib
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    args = parser.parse_args()

    output_path = pathlib.Path(args.output_file)
    for index in range(args.iterations):
        line = f"healthy_io {index}\n"
        print(line, end="", flush=True)
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
        time.sleep(args.delay_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
