"""Parse the extra browser origins an operator approves with ``--allow-origin``.

Each value names one exact origin (scheme, host and optional port) on a
loopback host. Wildcards, paths and public hosts are refused so that an
approval can never be wider than the address the operator copied.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

_SCHEMES = {"http": 80, "https": 443}


def _is_loopback_host(host: str) -> bool:
    """Return whether *host* is ``localhost``, a ``.localhost`` name or a loopback IP."""
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_extra_origin(value: str) -> str:
    """Return the normalised ``Origin`` form of an approved origin.

    The result is lower-case and omits the default port of its scheme,
    because browsers omit it from the ``Origin`` header.

    Args:
        value: The ``--allow-origin`` value, for example
            ``http://app.orca.localhost:57977``.

    Returns:
        The origin as a browser sends it.

    Raises:
        ValueError: The value is empty, has a wildcard, user information, a
            path, a query or a fragment, uses a scheme other than ``http`` or
            ``https``, has an invalid port, or names a host that is not a
            loopback name or address. The message names the broken rule.
    """
    text = value.strip()
    if not text:
        raise ValueError("Origin is empty. Give a value such as http://localhost:3000.")
    if "*" in text:
        raise ValueError(f"Origin {text!r} has a wildcard. Give one exact origin.")
    parts = urlsplit(text)
    scheme = parts.scheme
    if scheme not in _SCHEMES or not parts.netloc:
        raise ValueError(f"Origin {text!r} has an unsupported scheme. Use http or https.")
    if "@" in parts.netloc:
        raise ValueError(f"Origin {text!r} has user information. Remove it.")
    if parts.path not in {"", "/"}:
        raise ValueError(f"Origin {text!r} has a path. Give only scheme, host and port.")
    if parts.query:
        raise ValueError(f"Origin {text!r} has a query. Give only scheme, host and port.")
    if parts.fragment:
        raise ValueError(f"Origin {text!r} has a fragment. Give only scheme, host and port.")
    try:
        port = parts.port
    except ValueError:
        raise ValueError(f"Origin {text!r} has an invalid port. Use 0 to 65535.") from None
    host = parts.hostname
    if host is None or not _is_loopback_host(host):
        raise ValueError(
            f"Origin {text!r} is not a loopback origin. Use localhost, a .localhost name, "
            "127.0.0.1 or [::1]."
        )
    shown = f"[{host}]" if ":" in host else host
    origin = f"{scheme}://{shown}"
    if port is not None and port != _SCHEMES[scheme]:
        origin += f":{port}"
    return origin
