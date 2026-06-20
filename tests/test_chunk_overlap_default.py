"""Tests for retrieval defaults recorded in config.py.

Covers Section 3 of the rag-retrieval-quality-improvements OpenSpec change
and ADR-018 balanced retrieval defaults:
- Default CHUNK_OVERLAP is 100 (Stäbler et al. 2025 empirical sweet spot).
- The default still honours the CHUNK_OVERLAP env var when set.
- Default TOP_K is 10.
- Default RERANK_ENABLED is false (ADR-019: default-off for technical workloads).
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


def _extract_default_int_env(name: str) -> int:
    """Read an integer os.getenv default from config.py source."""
    src = _CONFIG_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf'{name}\s*=\s*int\(os\.getenv\("{name}",\s*"(\d+)"\)\)',
        src,
    )
    if match is None:
        raise AssertionError(f"Could not locate the {name} default in config.py")
    return int(match.group(1))


def _extract_default_bool_env(name: str) -> str:
    """Read a boolean os.getenv default from config.py source."""
    src = _CONFIG_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf'{name}\s*=\s*os\.getenv\("{name}",\s*"(true|false)"\)\.lower\(\)\s*==\s*"true"',
        src,
    )
    if match is None:
        raise AssertionError(f"Could not locate the {name} default in config.py")
    return match.group(1)


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


def test_balanced_retrieval_defaults_are_configured() -> None:
    """ADR-018/019 retrieval defaults SHALL be the codebase defaults."""
    assert _extract_default_chunk_overlap() == 100
    assert _extract_default_int_env("TOP_K") == 10
    assert _extract_default_bool_env("RERANK_ENABLED") == "false"


def test_balanced_retrieval_defaults_are_env_overridable() -> None:
    """TOP_K and RERANK_ENABLED SHALL remain environment-overridable."""
    src = _CONFIG_PATH.read_text(encoding="utf-8")
    assert 'os.getenv("TOP_K"' in src
    assert 'os.getenv("RERANK_ENABLED"' in src
