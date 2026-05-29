"""Tests for the bumped default `CHUNK_OVERLAP` value.

Covers Section 3 of the rag-retrieval-quality-improvements OpenSpec change:
- Default CHUNK_OVERLAP is 100 (Stäbler et al. 2025 empirical sweet spot).
- The default still honours the CHUNK_OVERLAP env var when set.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "src" / "rag_mcp" / "config.py"


def _extract_default_chunk_overlap() -> int:
    """Read the literal default for CHUNK_OVERLAP from the config source.

    Reloading ``rag_mcp.config`` is unreliable because ``load_dotenv()``
    re-reads the user's ``.env`` (which may pin the old value). Reading
    the source guarantees we are checking the codebase's documented
    default rather than the developer's local environment.
    """
    src = _CONFIG_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'CHUNK_OVERLAP\s*=\s*int\(os\.getenv\("CHUNK_OVERLAP",\s*"(\d+)"\)\)',
        src,
    )
    if match is None:
        raise AssertionError(
            "Could not locate the CHUNK_OVERLAP default in config.py"
        )
    return int(match.group(1))


def test_default_chunk_overlap_is_100() -> None:
    """The codebase default for ``CHUNK_OVERLAP`` SHALL be 100."""
    assert _extract_default_chunk_overlap() == 100


def test_chunk_overlap_env_override_shape() -> None:
    """The default SHALL be sourced through ``os.getenv`` so env vars win.

    This is a contract test — if the assignment changes shape (e.g.
    drops ``os.getenv``), the override behaviour silently regresses.
    """
    src = _CONFIG_PATH.read_text(encoding="utf-8")
    assert "CHUNK_OVERLAP" in src
    assert 'os.getenv("CHUNK_OVERLAP"' in src
