"""``omrs web start`` — load the login item again after Turn off.

OpenSpec change ``add-web-power-menu``. Turn off unloads the LaunchAgent
and keeps its plist; this command loads it again. Kept apart from
``web_login_item`` because that module sits at the file-size ceiling. It
reuses that module's helpers, so the fakes of the existing tests also
cover this command.
"""

from __future__ import annotations

import os

from rich.markup import escape

from . import _launchagent, console
from . import web_login_item as wl
from .web import web_app


@web_app.command()
def start() -> None:
    """Load the login item into launchd and wait for the app to answer.

    Use it after Turn off in the power panel. When the app already answers,
    the command changes nothing. The browser needs a new sign-in: run
    'omrs web open'.
    """
    if not wl._is_macos():
        wl._fail("Login items are macOS-only. 'omrs web start' needs macOS.")
    _, plan = wl._installed_plan()
    if plan is None:
        wl._fail("The login item is not installed. Run 'omrs web install' first.")

    uid = os.getuid()
    if wl.core.fetch_health(wl._HOST, wl._current_port(plan)) is not None:
        wl._say("The app is running. Nothing to start.")
        return

    # A loaded agent cannot be loaded twice. It is then only slow to start.
    if wl._launchctl(_launchagent.print_command(uid, plan.label)).returncode != 0:
        booted = wl._launchctl(_launchagent.bootstrap_command(uid, plan.plist_path))
        if booted.returncode != 0:
            wl._report_launchctl_failure("bootstrap", booted)
        console.print(f"[green]✓[/green] Loaded into gui/{uid}.")

    wl._say(f"Waiting up to {int(wl.START_TIMEOUT)} seconds for the app to answer...")
    body = wl._wait_for_health(lambda: wl._current_port(plan))
    if body is None:
        wl._fail(
            f"The app did not answer within {int(wl.START_TIMEOUT)} seconds. "
            f"Read the error log: {plan.stderr_log}. Run 'omrs web status' to check again."
        )
    version = escape(str(body.get("version", "?")))
    console.print(f"[green]✓[/green] The app is running (version {version}).")
    wl._say("Open it in your browser with: omrs web open")
