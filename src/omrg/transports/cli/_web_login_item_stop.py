"""Pure helpers for ``omrg web restart``: read the process id and poll until a condition holds.

Kept apart from ``web_login_item`` so that module stays under the file-size
ceiling. The clock and the sleep function are passed in, so the tests keep
their fake time.
"""

from __future__ import annotations

import re
from collections.abc import Callable

#: Seconds between two polls while waiting.
POLL_SECONDS = 1.0

# ``launchctl print`` shows the process id at the first indent level only.
_PID_LINE = re.compile(r"^\tpid = (\d+)$", re.M)


def parse_pid(returncode: int, stdout: str) -> int | None:
    """Return the process id from ``launchctl print`` output, or ``None``.

    A failed command or an output without a ``pid`` line means no process.
    """
    if returncode != 0:
        return None
    match = _PID_LINE.search(stdout)
    return int(match.group(1)) if match else None


def wait_until(
    done: Callable[[], bool],
    timeout: float,
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Poll *done* once per second until it is true or *timeout* seconds pass.

    *done* runs at least once, and once more at the deadline.
    """
    deadline = clock() + timeout
    while not done():
        if clock() >= deadline:
            return False
        sleep(POLL_SECONDS)
    return True
