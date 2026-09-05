"""Lightweight ingestion diagnostics used by bounded-memory benchmarks."""

from __future__ import annotations

import sys


def sample_peak_rss_bytes() -> int | None:
    """Return process peak RSS in bytes when the platform exposes it.

    ``resource.getrusage`` reports bytes on macOS and KiB on Linux/BSD.
    Windows does not provide the ``resource`` module, so callers receive
    ``None`` rather than gaining a platform-specific dependency.
    """
    try:
        import resource
    except ImportError:
        return None

    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return peak
    return peak * 1024
