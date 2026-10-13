"""Fail release preparation when a wheel lacks the built web assets.

Usage: ``python scripts/check_web_wheel.py dist/omrg-*.whl``

The web assets are gitignored build output (``npm run build`` in ``web/``).
Hatch ships them through ``artifacts`` when they exist, so a wheel built
without them is valid but cannot serve the workspace. This check makes
that omission fatal for a release.
"""

from __future__ import annotations

import re
import sys
import zipfile

STATIC_PREFIX = "omrg/transports/api/static/"
INDEX = STATIC_PREFIX + "index.html"
_ASSET_REF = re.compile(r'(?:src|href)="\./(assets/[^"]+)"')


def check_wheel(path: str) -> list[str]:
    """Return the problems found in one wheel; an empty list means it passes.

    Args:
        path: Path to a built ``.whl`` file.

    Returns:
        Human-readable problem descriptions.
    """
    with zipfile.ZipFile(path) as wheel:
        names = set(wheel.namelist())
        if INDEX not in names:
            return [f"{path}: missing {INDEX} (run `npm ci && npm run build` in web/)"]
        html = wheel.read(INDEX).decode("utf-8")
    referenced = _ASSET_REF.findall(html)
    if not referenced:
        return [f"{path}: {INDEX} references no ./assets/ files"]
    return [
        f"{path}: {INDEX} references missing {STATIC_PREFIX}{ref}"
        for ref in referenced
        if STATIC_PREFIX + ref not in names
    ]


def main(argv: list[str]) -> int:
    """Check each wheel named on the command line."""
    if not argv:
        print("usage: check_web_wheel.py WHEEL [WHEEL ...]", file=sys.stderr)
        return 2
    problems = [problem for path in argv for problem in check_wheel(path)]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
