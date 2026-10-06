"""The OCR engine contract and entry-point loading (design D1, D2).

An engine supplies only model-specific parsing and its identity
declarations. The core owns everything else: framing, validation, the
capability command, page-subset writing and error mapping.

An engine registers itself through exactly one entry point in the
``omrg.ocr_engine`` group. A worker environment with zero or several
registered engines is unavailable: the capability command exits with a
failure status, and the parse loop refuses to start.

This module must stay importable without Paddle or PyTorch. Loading an
engine imports its module, so engine modules import model code lazily,
inside ``parse``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

#: The entry-point group an engine registers in.
ENTRY_POINT_GROUP = "omrg.ocr_engine"

#: Operator variable that moves every engine's model cache out of the
#: engine folder (design D8). Engine ``<name>`` uses ``$VALUE/<name>/``.
MODEL_CACHE_ENV = "OMRG_OCR_MODEL_CACHE"

#: The cache folder inside an engine folder when the variable is unset.
MODEL_CACHE_DIRNAME = ".model-cache"


class WorkerParseError(Exception):
    """A parse failure that must surface as one terminal error envelope.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable description; the envelope bounds it.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EngineLoadError(Exception):
    """The environment does not register exactly one usable engine."""


@dataclass(frozen=True)
class DocumentMarkdown:
    """A whole-request result from an engine that assembles it itself.

    Attributes:
        markdown: Markdown for the whole request.
        pages_markdown: One Markdown string per requested page, in
            request order, for a page-listed request; ``None`` for a
            whole-document request.
        page_count: Number of pages the engine processed.
    """

    markdown: str
    pages_markdown: tuple[str, ...] | None
    page_count: int


@runtime_checkable
class OcrEngine(Protocol):
    """What one OCR engine supplies to the worker core (design D2).

    ``parse`` returns one Markdown string per parsed page: every page of
    the document when ``pages`` is ``None``, else the listed pages in
    order. An empty string marks a page the engine cannot read; the core
    passes it through.

    An engine MAY also define ``parse_document(pdf, pages) ->
    DocumentMarkdown``. The core then uses it instead of ``parse``. This
    hook exists for an engine that assembles the whole request itself,
    for example PaddleOCR-VL, which merges tables across pages.
    """

    name: str
    backend_id: str
    declared_packages: tuple[str, ...]
    pipeline: tuple[str, str]
    model: tuple[str, str]

    def parse(self, pdf: Path, pages: Sequence[int] | None) -> list[str]:
        """Return one Markdown string per parsed page."""
        ...


def registered_engine_names() -> list[str]:
    """Return the names of every entry point in the engine group, sorted."""
    return sorted(entry.name for entry in importlib_metadata.entry_points(group=ENTRY_POINT_GROUP))


def load_engine() -> OcrEngine:
    """Load the single engine this environment registers.

    Returns:
        The engine object the entry point names.

    Raises:
        EngineLoadError: If zero or several engines are registered, or
            the registered object does not satisfy the contract.
    """
    entries = list(importlib_metadata.entry_points(group=ENTRY_POINT_GROUP))
    if len(entries) != 1:
        names = ", ".join(sorted(entry.name for entry in entries)) or "none"
        raise EngineLoadError(
            f"expected exactly one {ENTRY_POINT_GROUP!r} entry point, found "
            f"{len(entries)} ({names})"
        )
    try:
        engine = entries[0].load()
    except Exception as exc:  # noqa: BLE001 - any import failure means unavailable
        raise EngineLoadError(
            f"cannot load engine {entries[0].name!r}: {type(exc).__name__}: {exc}"
        ) from exc
    validate_engine(engine)
    return engine


def validate_engine(engine: Any) -> None:
    """Check the static contract fields of an engine object.

    Raises:
        EngineLoadError: If a field is missing or has the wrong shape.
    """
    for field in ("name", "backend_id"):
        value = getattr(engine, field, None)
        if not isinstance(value, str) or not value:
            raise EngineLoadError(f"engine field {field!r} must be a non-empty string")
    packages = getattr(engine, "declared_packages", None)
    if not isinstance(packages, tuple) or not all(isinstance(p, str) and p for p in packages):
        raise EngineLoadError("engine field 'declared_packages' must be a tuple of names")
    for field in ("pipeline", "model"):
        pair = getattr(engine, field, None)
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(isinstance(part, str) and part for part in pair)
        ):
            raise EngineLoadError(f"engine field {field!r} must be an (identity, revision) pair")
    if not callable(getattr(engine, "parse", None)):
        raise EngineLoadError("engine must define parse(pdf, pages)")


def model_cache_dir(engine_name: str, engine_dir: Path) -> Path:
    """Return the model cache folder for one engine (design D8).

    Args:
        engine_name: The engine's registered name.
        engine_dir: The engine's project folder.

    Returns:
        ``$OMRG_OCR_MODEL_CACHE/<engine_name>`` when the variable is
        set and not blank, else ``<engine_dir>/.model-cache``.
    """
    root = os.environ.get(MODEL_CACHE_ENV, "").strip()
    if root:
        return Path(root).expanduser() / engine_name
    return engine_dir / MODEL_CACHE_DIRNAME
