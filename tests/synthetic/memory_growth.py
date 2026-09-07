import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=int, default=4)
    parser.add_argument("--chunk-kib", type=int, default=64)
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    args = parser.parse_args()

    chunks = []
    for index in range(args.chunks):
        chunks.append(bytearray(args.chunk_kib * 1024))
        print(f"memory_growth: chunk {index}", flush=True)
        time.sleep(args.delay_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
