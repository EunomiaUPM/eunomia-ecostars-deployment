"""Console output. Everything goes to stderr so stdout stays clean for data."""

from __future__ import annotations

import os
import sys

_COLOR = sys.stderr.isatty() and os.environ.get("NO_COLOR") is None


class Abort(SystemExit):
    """Raised by fail(); carries exit code 1 and prints nothing more."""

    def __init__(self) -> None:
        super().__init__(1)


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def step(msg: str) -> None:
    print(_paint("36", f"\n{msg}"), file=sys.stderr)


def ok(msg: str) -> None:
    print(_paint("32", msg), file=sys.stderr)


def info(msg: str) -> None:
    print(_paint("33", msg), file=sys.stderr)


def warn(msg: str) -> None:
    print(_paint("35", f"warning: {msg}"), file=sys.stderr)


def fail(msg: str) -> "Abort":
    """Print an error and abort. Returns the exception so callers can `raise fail(...)`."""
    print(_paint("31", msg), file=sys.stderr)
    return Abort()
