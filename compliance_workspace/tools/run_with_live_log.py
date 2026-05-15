"""Run a command while streaming output to console plus log files."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream a command to console and logs.")
    parser.add_argument("--append-log", required=True)
    parser.add_argument("--latest-log", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if not args.command:
        parser.error("missing command")

    if args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command after --")

    append_log = Path(args.append_log)
    latest_log = Path(args.latest_log)
    append_log.parent.mkdir(parents=True, exist_ok=True)
    latest_log.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    with append_log.open("a", encoding="utf-8", errors="replace") as append_fh:
        with latest_log.open("w", encoding="utf-8", errors="replace") as latest_fh:
            proc = subprocess.Popen(
                args.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                append_fh.write(line)
                append_fh.flush()
                latest_fh.write(line)
                latest_fh.flush()
            return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
