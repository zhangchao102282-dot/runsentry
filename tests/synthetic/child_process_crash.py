import argparse
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-exit-code", type=int, default=0)
    parser.add_argument("--child-exit-code", type=int, default=7)
    parser.add_argument("--linger-seconds", type=float, default=0.5)
    args = parser.parse_args()

    child = subprocess.Popen(
        [sys.executable, "-c", f"raise SystemExit({args.child_exit_code})"]
    )
    child.wait(timeout=5)
    print(f"child_process_crash: child exited {child.returncode}", flush=True)
    time.sleep(args.linger_seconds)
    return args.root_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
