"""Loopback-only bind address check for the web transport (design D8).

:func:`validate_bind_host` lives in its own module so ``security.py`` stays
under the 500-line ceiling (persistent-web-auth-token, design D3).
"""

from __future__ import annotations

import ipaddress

_LOOPBACK_NAMES = {"localhost": "127.0.0.1"}


def validate_bind_host(host: str) -> str:
    """Return the loopback address to bind, or refuse a remote address.

    Args:
        host: The requested bind address or ``localhost``.

    Returns:
        The literal loopback address to bind.

    Raises:
        ValueError: The address is not a loopback address.
    """
    candidate = _LOOPBACK_NAMES.get(host.strip().lower(), host.strip())
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is None or not address.is_loopback:
        raise ValueError(
            f"Refusing to bind to {host!r}: the web workspace is for local use and "
            "binds only to a loopback address (127.0.0.1, ::1 or localhost). "
            "Use an SSH tunnel if you need to reach it from another machine."
        )
    return str(address)
