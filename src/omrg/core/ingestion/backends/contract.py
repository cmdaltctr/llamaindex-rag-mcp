"""Shared async contract for document-backend strategies.

One callable shape backs every registered ``DOCUMENT_BACKEND``
implementation (spec ``document-backend-strategies``: "Document backends
use one configured contract"), so ``local`` and ``azure`` stay
interchangeable at the dispatch boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ...settings import EffectiveSettings


class DocumentBackend(Protocol):
    """Async document-reading contract shared by every registered backend.

    Implementations read one file and return LlamaIndex ``Document``
    objects whose metadata carries at least ``file_path`` (the parity
    fixture in ``tests/test_document_backends.py`` pins the required
    fields).  Adapters receive the frozen :class:`EffectiveSettings`
    value object — never a settings singleton (ADR-037) — and must
    offload blocking parser work with ``asyncio.to_thread`` so the
    event loop stays responsive.
    """

    async def __call__(self, file_path: Path, *, settings: EffectiveSettings) -> list[Any]: ...
