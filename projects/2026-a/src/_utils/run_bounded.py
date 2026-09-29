"""Run one authorized project command with a 59-minute wall-clock ceiling.

This wrapper provides a resource limit, not execution authorization. Model and
verification calls must still enter through skills/scripts/run_authorized_action.py.
The exact child argv is part of that enclosing runtime action.
"""
import argparse
import os
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-s", type=float, default=3540.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not 0 < args.limit_s <= 3540 or not command:
        parser.error("A child command and 0 < limit <= 3540 seconds are required")
    started = time.monotonic()
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    child = subprocess.Popen(command, **options)
    try:
        return child.wait(timeout=args.limit_s)
    except subprocess.TimeoutExpired:
        print(f"Project computation stopped at the {args.limit_s:g}s limit; no successful result is inferred.", file=sys.stderr, flush=True)
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                           timeout=15, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=15)
        return 124
    finally:
        print(f"Bounded command elapsed: {time.monotonic() - started:.3f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
