"""The integration catalogue for ``GET /v1/integrations`` (design D7).

The catalogue is declared once, here. It has one entry for each installable
extra in ``pyproject.toml`` plus the always-on Magika integration. Each
entry carries a probe. The probes reuse the runtime probes the server
already owns (``omrs.capabilities`` for modules, PDF readers and Magika;
the vector-store and community registries). A probe that raises gives the
``unknown`` state, never an error response, and no probe text is returned.

Each entry also says whether the app can install its extra
(``installable`` and ``install_reason``), the requirements it would add
(``packages``) and the copy command for this install type
(``install_command``, design D4). An extra installed by the app in this
launch reports ``restart-needed``. Nothing here installs a package: the
install job lives in ``install_job.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

from ... import capabilities
from .install_environment import (
    InstallEnvironment,
    copy_command,
    extra_requirements,
    install_reason,
    is_base_extra,
)

logger = logging.getLogger(__name__)

AVAILABLE = "available"
NOT_INSTALLED = "not-installed"
UNKNOWN = "unknown"
RESTART_NEEDED = "restart-needed"

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
        caution: A warning the page shows before the install, or ``None``.
    """

    id: str
    name: str
    purpose: str
    extra: str | None
    probe: Probe
    caution: str | None = None


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
        # botocore (through anthropic[bedrock]) needs python-dateutil<3 (ADR-094).
        "This install can change another package. It adds Amazon's botocore, which "
        "needs python-dateutil below version 3, so uv can move python-dateutil back "
        "to 2.9. The app checks every package after the install.",
    ),
    Integration(
        "torch",
        "PyTorch reranker",
        "Optional PyTorch backend for the cross-encoder reranker.",
        "torch",
        _modules("sentence_transformers", "transformers"),
        # Sizes from uv.lock (torch 2.13, macOS arm64 wheels) and the CUDA builds.
        "This install is large. On a Mac, PyTorch and its libraries download about "
        "170 MB. On Linux with GPU support they can take several GB. Search uses "
        "PyTorch only when retrieval.rerank_backend is set to torch.",
    ),
    Integration(
        "web",
        "Local web workspace",
        "The FastAPI server that runs `omrs web`.",
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


def find_integration(extra: str) -> Integration | None:
    """Return the catalogue entry whose extra is *extra*, or ``None``."""
    return next((item for item in CATALOGUE if item.extra and item.extra == extra), None)


def describe_entry(
    item: Integration,
    settings: Any,
    environment: InstallEnvironment,
    restart_needed: Collection[str] = (),
    requirements: Callable[[str], list[str]] = extra_requirements,
) -> dict[str, Any]:
    """Return one catalogue entry with its availability and install fields.

    Args:
        item: The catalogue entry.
        settings: The Engine's frozen ``EffectiveSettings``, or ``None``.
        environment: The detected install type and ``uv`` program.
        restart_needed: Extras the app installed in this launch.
        requirements: Returns an extra's requirements.
    """
    extra = item.extra
    if extra is not None and extra in restart_needed:
        availability = RESTART_NEEDED
    else:
        try:
            availability = item.probe(settings)
        except Exception:
            # Detail stays in the (redacted) log. The client gets the state only.
            logger.warning("Integration probe %r failed.", item.id, exc_info=True)
            availability = UNKNOWN
    packages = [] if extra is None else requirements(extra)
    # A base entry comes with every install; offering it again would install it twice.
    base = is_base_extra(extra)
    reason = (
        "not-installable-here"
        if base
        else install_reason(extra, availability, packages, environment)
    )
    return {
        "id": item.id,
        "name": item.name,
        "purpose": item.purpose,
        "extra": extra,
        "base": base,
        "install_command": None if base or extra is None else copy_command(environment, extra),
        "pip_command": None if base or extra is None else f'pip install "omrs[{extra}]"',
        "availability": availability,
        "installable": reason is None,
        "install_reason": reason,
        "packages": packages,
        "install_caution": item.caution,
    }


def describe_integrations(
    settings: Any | None,
    environment: InstallEnvironment,
    restart_needed: Collection[str] = (),
    requirements: Callable[[str], list[str]] = extra_requirements,
) -> list[dict[str, Any]]:
    """Return every catalogue entry with its resolved availability.

    Args:
        settings: The Engine's frozen ``EffectiveSettings``, or ``None``
            when they cannot be read (the Magika probe then reports
            ``unknown``).
        environment: The detected install type and ``uv`` program.
        restart_needed: Extras the app installed in this launch.
        requirements: Returns an extra's requirements.
    """
    return [
        describe_entry(item, settings, environment, restart_needed, requirements)
        for item in CATALOGUE
    ]
