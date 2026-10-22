"""Power control for the web login item (design D1, D2, D6 of ``add-web-power-menu``).

Two actions exist, each mapped to one launchd step:

* ``restart`` sends ``SIGTERM`` with ``launchctl kill``. Uvicorn ends by
  signal, so launchd starts the app again by itself.
* ``off`` runs ``launchctl bootout``. launchd unloads the agent, so
  ``KeepAlive`` has nothing to restart. The plist stays on disk.

The API must not import from ``transports/cli``, so this module builds the
two argv lists itself. ``tests/unit/test_power_control.py`` compares them
with ``_launchagent.kill_command`` and ``_launchagent.bootout_command``,
which keeps the two copies in step.

The runner uses a fixed argument list, no shell and a timeout. It never
raises: the caller has gone by the time it runs.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RESTART = "restart"
OFF = "off"
#: The closed set of actions a request may name.
ACTIONS: tuple[str, ...] = (RESTART, OFF)

#: Seconds the server waits after it answers, so the response and the
#: browser's next poll leave before the process ends (design D2).
ACT_DELAY_SECONDS = 0.5
#: Seconds one launchctl call may take.
RUN_TIMEOUT_SECONDS = 10.0


def build_argv(action: str, uid: int, label: str) -> list[str]:
    """Return the launchctl argv for *action*.

    Args:
        action: ``restart`` or ``off``.
        uid: User id of the GUI domain that holds the agent.
        label: Launchd label of the agent.

    Returns:
        A fixed argument list for ``subprocess.run`` with no shell.

    Raises:
        ValueError: *action* is not one of :data:`ACTIONS`.
    """
    target = f"gui/{uid}/{label}"
    if action == RESTART:
        return ["launchctl", "kill", "SIGTERM", target]
    if action == OFF:
        return ["launchctl", "bootout", target]
    raise ValueError(f"Unknown power action: {action!r}")


def run_argv(argv: list[str], timeout: float = RUN_TIMEOUT_SECONDS) -> int | None:
    """Run *argv* with no shell and a timeout, and never raise.

    Args:
        argv: The argument list to run.
        timeout: Seconds before the call is abandoned.

    Returns:
        The exit status, or ``None`` when the call could not run or timed out.
        A failure is logged and nothing else happens.
    """
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv built from a closed action set, no shell
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Power control could not run %s: %s", argv[:2], type(exc).__name__)
        return None
    if done.returncode != 0:
        logger.warning(
            "Power control: launchctl %s ended with exit %d.", argv[1:2], done.returncode
        )
    return done.returncode


@dataclass(frozen=True)
class PowerControl:
    """What the server needs to act on its own login item.

    ``web.py`` sets one on ``application.state.power_control`` only when the
    app runs as the login item. Its presence is what ``managed`` means.

    Attributes:
        label: Launchd label of the login item.
        uid: User id of the GUI domain.
        runner: Runs an argv. Tests pass a fake that records it.
        delay: Seconds to wait after the response before acting.
        sleep: Awaitable sleep. Tests pass a fake.
    """

    label: str
    uid: int
    runner: Callable[[list[str]], object] = run_argv
    delay: float = ACT_DELAY_SECONDS
    sleep: Callable[[float], Awaitable[object]] = field(default=asyncio.sleep, compare=False)

    def argv(self, action: str) -> list[str]:
        """Return the launchctl argv for *action*."""
        return build_argv(action, self.uid, self.label)

    async def act(self, action: str) -> None:
        """Wait for the delay, then run the argv for *action*. Never raises."""
        try:
            await self.sleep(self.delay)
            await asyncio.to_thread(self.runner, self.argv(action))
        except Exception:
            logger.exception("Power action %r failed.", action)
