"""Portable command-line runner with a total wall-clock limit."""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("q1", "q23", "q4", "all"), default="all")
    parser.add_argument("--output", type=Path, default=Path("recomputed"))
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--n", type=int, help="Radial intervals; default Q1=5120, Q23/Q4=10240")
    parser.add_argument("--tight", action="store_true", help="Use the existing tighter time-error settings")
    parser.add_argument("--tail", choices=("mean_tail", "last_value"), default="mean_tail")
    parser.add_argument("--radius", choices=("linear", "pchip", "constant"), default="linear")
    parser.add_argument("--timeout", type=float, default=3300.0, help="Total wall-clock budget in seconds, strictly below one hour")
    parser.add_argument("--no-xlsx", action="store_true", help="Save unrounded NPZ/settings only")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 3300:
        parser.error("--timeout must be in (0,3300] seconds")
    if args.n is not None and (args.n < 20 or args.n % 20):
        parser.error("--n must be a positive multiple of 20")
    cases = ("q1", "q23", "q4") if args.case == "all" else (args.case,)
    if args.worker:
        if args.case == "all":
            parser.error("Worker accepts one calculation")
        if args.case == "q1":
            from q1_model import run
            run(args.n or 5120, args.output, args.data, tight=args.tight)
        elif args.case == "q23":
            from q23_model import run
            run(args.n or 10240, args.output, args.data, tight=args.tight, scenario=args.tail)
        else:
            from q4_model import run
            run(args.n or 10240, args.output, args.data, tight=args.tight,
                scenario=args.tail, radius_method=args.radius)
        if not args.no_xlsx:
            from export_results import export_case
            for path in export_case(args.case, args.output, args.data):
                print(path, flush=True)
        return
    # The entire command, including --case all, shares one wall-clock budget.
    deadline = time.monotonic() + args.timeout
    for case in cases:
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", "--case", case,
                   "--output", str(args.output.resolve()), "--data", str(args.data.resolve()),
                   "--tail", args.tail, "--radius", args.radius, "--timeout", str(args.timeout)]
        if args.n is not None:
            command += ["--n", str(args.n)]
        if args.tight:
            command.append("--tight")
        if args.no_xlsx:
            command.append("--no-xlsx")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SystemExit("Total wall-clock budget exhausted; calculation stopped")
        try:
            subprocess.run(command, check=True, timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise SystemExit(f"{case}: exceeded {args.timeout:g} seconds; calculation stopped") from exc


if __name__ == "__main__":
    main()
