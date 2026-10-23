"""Unit tests for the admission counter (task 1.2 of ``add-web-power-menu``)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastapi")

from omrs.transports.api import lifespan  # noqa: E402
from omrs.transports.api.admission import Admission, AdmissionClosed  # noqa: E402


def test_lifespan_re_exports_the_moved_names() -> None:
    """Existing imports and patch targets keep working after the move."""
    assert lifespan.Admission is Admission
    assert lifespan.AdmissionClosed is AdmissionClosed


def test_active_counts_admitted_calls_and_returns_to_zero() -> None:
    """``active`` is the number of calls inside ``enter`` and is 0 at the end."""

    async def scenario() -> list[int]:
        admission = Admission()
        seen = [admission.active]
        async with admission.enter():
            seen.append(admission.active)
            async with admission.enter():
                seen.append(admission.active)
            seen.append(admission.active)
        seen.append(admission.active)
        return seen

    assert asyncio.run(scenario()) == [0, 1, 2, 1, 0]


def test_active_returns_to_zero_when_the_block_raises() -> None:
    async def scenario() -> int:
        admission = Admission()
        with pytest.raises(RuntimeError):
            async with admission.enter():
                raise RuntimeError("boom")
        return admission.active

    assert asyncio.run(scenario()) == 0


def test_active_is_read_only() -> None:
    admission = Admission()
    with pytest.raises(AttributeError):
        admission.active = 5  # type: ignore[misc]
