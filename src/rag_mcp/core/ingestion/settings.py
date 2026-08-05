"""Pure-data settings model for the ingestion subpackage.

``embed_concurrency`` and ``embed_batch_size`` previously lived in
``ChunkingSettings``, where the flat schema had nowhere better to put them.
They are ingestion concerns, not chunking concerns, and the nested schema
gives them a home (design.md D10). The move is made in the same change as the
env-var rename so the migration cost is paid once rather than twice.

This module MUST stay pure data: no imports from ``config``, ``compose``, or
any sibling ``core/`` business module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IngestionSettings(BaseModel):
    """Ingestion pipeline knobs (env prefix ``INGESTION__``)."""

    model_config = ConfigDict(extra="forbid")

    # Number of parallel embedding requests in flight.
    embed_concurrency: int = 2

    # Documents per embedding API call.
    embed_batch_size: int = 100
