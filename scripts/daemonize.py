#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start a command as a detached local daemon.")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.cmd:
        raise SystemExit("missing command")

    pid = os.fork()
    if pid > 0:
        return

    os.setsid()
    pid = os.fork()
    if pid > 0:
        os._exit(0)

    os.chdir(args.cwd)
    os.umask(0o022)
    os.makedirs(os.path.dirname(args.pid_file), exist_ok=True)
    os.makedirs(os.path.dirname(args.log_file), exist_ok=True)

    with open(args.pid_file, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
        fh.write("\n")

    devnull = os.open(os.devnull, os.O_RDONLY)
    logfile = os.open(args.log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(devnull, 0)
    os.dup2(logfile, 1)
    os.dup2(logfile, 2)
    os.close(devnull)
    os.close(logfile)

    os.execvp(args.cmd[0], args.cmd)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"daemonize failed: {exc}", file=sys.stderr)
        raise
