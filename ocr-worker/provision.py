#!/usr/bin/env python3
"""Deterministic provisioning for the isolated OCR worker environment.

Resolves the worker virtual environment from the worker-owned
``uv.lock`` only. The script never touches the parent OMRG project or
its virtual environment: every command runs with this directory as
its working directory, and ``uv sync --locked`` refuses drift from the
committed lockfile.

Usage::

    python3 provision.py                # provision with Python 3.12
    python3 provision.py --python 3.11  # provision with a specific version
    python3 provision.py --python 3.13

Supported interpreters: Python 3.11, 3.12, and 3.13 (the range the
worker manifest declares, ``>=3.11,<3.14``). Any other version is
rejected with an error naming the supported range before anything is
installed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED_MIN = (3, 11)
SUPPORTED_MAX_INCLUSIVE = (3, 13)
SUPPORTED_RANGE_TEXT = ">=3.11,<3.14"

WORKER_DIR = Path(__file__).resolve().parent


class UnsupportedPythonError(Exception):
    """The requested interpreter is outside the supported range.

    Attributes:
        version: The rejected ``(major, minor)`` version.
    """

    def __init__(self, version: tuple[int, int]) -> None:
        self.version = version
        super().__init__(
            f"Python {version[0]}.{version[1]} is not supported by the OCR "
            f"worker. Use a Python version in the range {SUPPORTED_RANGE_TEXT} "
            "(3.11, 3.12, or 3.13)."
        )


def parse_python_version(text: str) -> tuple[int, int]:
    """Extract the ``(major, minor)`` version from a version string.

    Args:
        text: A version such as ``3.12``, ``3.12.7``, or the leading
            part of a ``sys.version`` string.

    Returns:
        The ``(major, minor)`` pair.

    Raises:
        ValueError: If no ``major.minor`` prefix can be read.
    """
    parts = text.strip().split()
    candidate = parts[0] if parts else text.strip()
    segments = candidate.split(".")
    try:
        major = int(segments[0])
        minor = int(segments[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"cannot read a major.minor version from {text!r}") from exc
    return (major, minor)


def ensure_supported_python(version: tuple[int, int]) -> None:
    """Accept a supported interpreter version or reject it clearly.

    Args:
        version: The ``(major, minor)`` interpreter version.

    Raises:
        UnsupportedPythonError: If the version is outside
            ``>=3.11,<3.14``, naming the supported range.
    """
    if not (SUPPORTED_MIN <= version <= SUPPORTED_MAX_INCLUSIVE):
        raise UnsupportedPythonError(version)


def main(argv: list[str] | None = None) -> int:
    """Provision the worker environment from the worker-owned lockfile.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(
        description="Provision the isolated OCR worker environment from uv.lock."
    )
    parser.add_argument(
        "--python",
        default="3.12",
        help="Python version or interpreter path (default: 3.12)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve from the lockfile without installing anything",
    )
    args = parser.parse_args(argv)

    requested = args.python
    if Path(requested).exists():
        # An explicit interpreter path: ask it for its own version.
        probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [requested, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            print(f"error: cannot interrogate interpreter {requested!r}", file=sys.stderr)
            return 1
        requested = probe.stdout.strip()

    try:
        version = parse_python_version(requested)
        ensure_supported_python(version)
    except (UnsupportedPythonError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if shutil.which("uv") is None:
        print(
            "error: uv is not on PATH; install it from https://docs.astral.sh/uv/",
            file=sys.stderr,
        )
        return 1

    command = ["uv", "sync", "--locked", "--python", args.python]
    if args.dry_run:
        command.append("--dry-run")
    print(f"provisioning OCR worker with Python {version[0]}.{version[1]} ...")
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command, cwd=WORKER_DIR, check=False
    )
    if completed.returncode != 0:
        print("error: provisioning failed; see the uv output above", file=sys.stderr)
        return completed.returncode
    print("OCR worker environment ready (resolved from uv.lock only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
