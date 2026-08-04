"""Profiles system — dual use-case support (Phase 4 refactor, ADR-030).

Provides per-collection profile resolution so one server process can serve
both document grounding (Use Case A) and codebase context (Use Case B)
simultaneously.  Each ChromaDB collection carries an optional profile tag
in its metadata; the :class:`ProfileResolver` maps a collection name to
its effective Tier 2 levers at operation time.

Public API:
    * :class:`EffectiveSettings` — the per-operation Tier 2 lever bundle.
    * :class:`ProfileResolver` — maps ``collection_name → EffectiveSettings``.

See ``docs/adr/030-phase-4-refactor-profiles-dual-use-case.md`` for the
full design rationale (two-tier resolution, non-destructive changes,
transport-specific safety contract).
"""

from __future__ import annotations

from .contract import apply_profile_change, generate_safety_contract
from .resolver import EffectiveSettings, ProfileResolver

__all__ = [
    "EffectiveSettings",
    "ProfileResolver",
    "generate_safety_contract",
    "apply_profile_change",
]
