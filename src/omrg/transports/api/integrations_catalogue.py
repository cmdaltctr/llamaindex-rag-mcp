"""The integration catalogue for ``GET /v1/integrations`` (design D7).

The catalogue is declared once, here. It has one entry for each installable
extra in ``pyproject.toml`` plus the always-on Magika integration. Each
entry carries a probe. The probes reuse the runtime probes the server
already owns (``omrg.capabilities`` for modules, PDF readers and Magika;
the vector-store and community registries). A probe that raises gives the
``unknown`` state, never an error response, and no probe text is returned.

The page shows availability and install commands. Nothing here installs,
downloads or changes a package.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ... import capabilities

logger = logging.getLogger(__name__)

AVAILABLE = "available"
NOT_INSTALLED = "not-installed"
UNKNOWN = "unknown"

#: ``settings`` is the Engine's frozen ``EffectiveSettings``, or ``None``.
Probe = Callable[[Any], str]


def _modules(*names: str) -> Probe:
    """Probe that is available when every named module resolves."""

    def probe(_: Any) -> str:
        found = all(capabilities.module_installed(name) for name in names)
        return AVAILABLE if found else NOT_INSTALLED

    return probe


def _chroma(_: Any) -> str:
    from ...core.vectordb import registry

    state = registry.availability("chroma")
    if state == "available":
        return AVAILABLE
    return NOT_INSTALLED if state in {"absent", "partial"} else UNKNOWN


def _pdf_reader(reader: str) -> Probe:
    def probe(_: Any) -> str:
        return AVAILABLE if capabilities.pdf_reader_installed(reader) else NOT_INSTALLED

    return probe


def _leiden(_: Any) -> str:
    from ...core.community import registry

    try:
        registry.verify_available("leiden")
    except ImportError:
        return NOT_INSTALLED
    return AVAILABLE


def _magika(settings: Any) -> str:
    return AVAILABLE if capabilities.magika_available(settings) else NOT_INSTALLED


@dataclass(frozen=True)
class Integration:
    """One catalogue entry.

    Attributes:
        id: Stable identifier (the extra name, or ``magika``).
        name: Display name.
        purpose: One-line description of what the integration adds.
        extra: The pip extra, or ``None`` for an always-on integration.
        probe: Returns ``available``, ``not-installed`` or ``unknown``.
    """

    id: str
    name: str
    purpose: str
    extra: str | None
    probe: Probe


CATALOGUE: tuple[Integration, ...] = (
    Integration(
        "chroma",
        "Chroma vector store",
        "Optional Chroma backend for indexes that already use it.",
        "chroma",
        _chroma,
    ),
    Integration(
        "hybrid",
        "Hybrid search",
        "BM25 keyword scoring that joins vector search results.",
        "hybrid",
        _modules("rank_bm25"),
    ),
    Integration(
        "pdf-pypdfium2",
        "PDF reader: pypdfium2",
        "Reads PDF pages with the pypdfium2 library.",
        "pdf-pypdfium2",
        _pdf_reader("pypdfium2"),
    ),
    Integration(
        "pdf-inspector",
        "PDF reader: pdf-inspector",
        "Reads PDF files as Markdown with the pdf-inspector library.",
        "pdf-inspector",
        _pdf_reader("pdf_inspector"),
    ),
    Integration(
        "community-leiden",
        "Leiden communities",
        "Leiden community detection for codebase and document graphs.",
        "community-leiden",
        _leiden,
    ),
    Integration(
        "azure",
        "Azure Document Intelligence",
        "Cloud document reading through Azure Document Intelligence.",
        "azure",
        _modules("azure.ai.documentintelligence"),
    ),
    Integration(
        "llamacpp",
        "llama.cpp provider",
        "Embedding and chat models served by a llama.cpp server.",
        "llamacpp",
        _modules("llama_index.embeddings.openai_like", "llama_index.llms.openai_like"),
    ),
    Integration(
        "openrouter",
        "OpenRouter provider",
        "Cloud embedding and chat models through OpenRouter.",
        "openrouter",
        _modules("llama_index.embeddings.openai_like", "llama_index.llms.openai_like"),
    ),
    Integration(
        "anthropic",
        "Anthropic provider",
        "Chat answers from Anthropic models.",
        "anthropic",
        _modules("llama_index.llms.anthropic"),
    ),
    Integration(
        "torch",
        "PyTorch reranker",
        "Optional PyTorch backend for the cross-encoder reranker.",
        "torch",
        _modules("sentence_transformers", "transformers"),
    ),
    Integration(
        "web",
        "Local web workspace",
        "The FastAPI server that runs `omrg web`.",
        "web",
        _modules("fastapi", "uvicorn"),
    ),
    Integration(
        "magika",
        "Magika file detection",
        "Detects file types for codebase maps. Part of the base install.",
        None,
        _magika,
    ),
)


def _entry(item: Integration, settings: Any) -> dict[str, Any]:
    try:
        availability = item.probe(settings)
    except Exception:
        # Detail stays in the (redacted) log. The client gets the state only.
        logger.warning("Integration probe %r failed.", item.id, exc_info=True)
        availability = UNKNOWN
    extra = item.extra
    return {
        "id": item.id,
        "name": item.name,
        "purpose": item.purpose,
        "extra": extra,
        "install_command": None if extra is None else f"uv sync --extra {extra}",
        "pip_command": None if extra is None else f'pip install "omrg[{extra}]"',
        "availability": availability,
    }


def describe_integrations(settings: Any | None) -> list[dict[str, Any]]:
    """Return every catalogue entry with its resolved availability.

    Args:
        settings: The Engine's frozen ``EffectiveSettings``, or ``None``
            when they cannot be read (the Magika probe then reports
            ``unknown``).
    """
    return [_entry(item, settings) for item in CATALOGUE]
