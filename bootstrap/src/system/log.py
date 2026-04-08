"""
role:
    Timestamped console output helpers used throughout the bootstrap.

responsibilities:
    - emit levelled log lines (INFO, OK, WARN, ERROR) with timestamps
    - print section headers to stdout

does_not:
    - write to files or syslog
    - control log verbosity or filtering

side_effects:
    - section/info/ok/warn write to stdout; error writes to stderr
"""
from __future__ import annotations

import datetime
import sys


def section(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def info(msg: str) -> None:
    _log("INFO ", msg)


def ok(msg: str) -> None:
    _log("OK   ", msg)


def warn(msg: str) -> None:
    _log("WARN ", msg)


def error(msg: str) -> None:
    _log("ERROR", msg, file=sys.stderr)


def _log(level: str, msg: str, file=sys.stdout) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {level} {msg}", file=file, flush=True)
