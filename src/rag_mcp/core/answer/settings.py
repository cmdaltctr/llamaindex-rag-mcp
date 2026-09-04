"""Answer settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the ``core/answer``
subpackage (the grounded answering operation).  Consumed by the root
``Settings`` resolver in ``rag_mcp.config``.  MUST NOT import from
``config``, ``compose``, or any other ``core/`` module (enforced by
import-linter).

Mirrors :class:`rag_mcp.core.settings.AnswerBlock` (the frozen
``EffectiveSettings`` block); both models must stay in sync — the
MetadataSettings/MetadataBlock pair established the convention.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _parse_legacy_bool(value: object) -> object:
    """Parse booleans using legacy ``.lower() == "true"`` semantics."""
    if isinstance(value, str):
        return value.lower() == "true"
    return value


LegacyBool = Annotated[bool, BeforeValidator(_parse_legacy_bool)]


class AnswerSettings(BaseModel):
    """Configuration knobs for the grounded answering operation.

    Every value defaults to something that works with the existing
    local-first provider configuration: the base-install ollama
    provider, a small local model, and client sampling preferred when
    the MCP client offers one.
    """

    model_config = ConfigDict(extra="forbid")

    # ── Availability ────────────────────────────────────────────────
    # When false, ``compose.build_answer_llm`` resolves to ``None`` and
    # the answering tools return an actionable error naming the setting.
    enabled: LegacyBool = True

    # ── Server-side model ───────────────────────────────────────────
    # Provider name resolved through ``core/providers/llm/registry.py``
    # (the same registry metadata extraction uses); validated at startup
    # by ``compose._resolve_active_strategies`` so a bad name fails fast.
    provider: str = "ollama"
    # Model tag handed to the provider builder via the backwards-
    # compatible ``answer_model`` override so answering never silently
    # reuses the metadata classification model.
    model: str = "qwen3:4b"
    # Seconds to wait for one completion round.
    timeout: float = Field(default=120.0, gt=0)

    # ── Synthesis bounds ────────────────────────────────────────────
    # COMPACT may refine across multiple completion rounds.  Rounds are
    # bounded by ``max_rounds`` (1..8; the MCP client chain is further
    # capped at the resolver-chain depth); ``context_window`` is the
    # per-round context budget in CHARACTERS (a deterministic character
    # count, not a tokenizer estimate).  When the evidence needs more
    # rounds than the bound allows, later rounds absorb the overflow
    # rather than dropping evidence.
    max_rounds: int = Field(default=4, ge=1, le=8)
    context_window: int = Field(default=8192, gt=0)
    # Reserved head-room for the model's reply inside one round's budget.
    max_output_tokens: int = Field(default=2048, gt=0)

    # ── MCP client sampling ─────────────────────────────────────────
    # Prefer the client's model (MRTR resolver on a modern session) over
    # the configured server-side model when the client advertises the
    # sampling capability.
    prefer_client_sampling: LegacyBool = True
    # Allow the deprecated ``ctx.session.create_message`` back-channel
    # ONLY on a negotiated pre-2026-07-28 session (explicit compatibility
    # mode; never attempted on a modern session).
    allow_legacy_sampling: LegacyBool = True

    # ── Claim verification (opt-in cloud judge — ADR-059) ──────────
    # Off by default: the judge needs a cloud model (experiment 20
    # showed a local qwen3:4b judge infeasible on consumer hardware),
    # which is an explicit opt-in against ADR-024's local-first policy.
    verify_claims: LegacyBool = False
    # Empty string derives the judge model from the provider's default
    # (e.g. ``openrouter_llm_model``); set to pin a specific judge.
    verify_model: str = ""
    # Alias resolved like ``metadata_llm_provider``: "cloud" (or empty)
    # → the cloud backend, "local" → the local backend, anything else
    # is a literal LLM-registry name validated at startup.
    verify_provider: str = "cloud"
