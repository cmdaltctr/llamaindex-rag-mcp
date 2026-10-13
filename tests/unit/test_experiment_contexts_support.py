"""Shared helpers for the experiment context tests (task 8.5).

The helpers build explicit ``Settings`` with no ``.env`` and an engine
builder that honours the store location in those settings. Engines use
tmp_path LanceDB stores and the conftest mock embedder. This module holds
no tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from llama_index.core import Settings as LlamaIndexSettings

from omrg.compose_settings import settings_to_effective
from omrg.config import Settings
from omrg.core.metadata.settings import MetadataSettings
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.engine import Engine


def base_settings(live_dir: Path) -> Settings:
    """Return offline settings whose live library is *live_dir*."""
    return Settings(
        _env_file=None,
        vector_store="lancedb",
        lancedb_uri=str(live_dir),
        pdf_reader="pypdf",
        ocr_fallback_enabled=False,
        metadata=MetadataSettings(extraction_mode="disabled"),
    )


def new_embedder() -> Any:
    """Return a new instance of the conftest unit-norm mock embedder."""
    return type(LlamaIndexSettings.embed_model)(embed_dim=384)


class RecordingBuilder:
    """Engine builder that honours the settings it receives.

    It builds the store from ``settings.lancedb_uri``, so a builder call
    with the live settings would write to the live directory. Tests read
    ``calls`` to prove which settings composition passed.
    """

    def __init__(self, effective_overrides: dict[str, Any] | None = None) -> None:
        """Start with no calls."""
        self.calls: list[Settings] = []
        self.engines: list[Engine] = []
        self._overrides = effective_overrides or {}

    def __call__(self, settings: Settings) -> Engine:
        """Build an Engine over a LanceDB store at the settings location."""
        self.calls.append(settings)
        effective = settings_to_effective(settings).model_copy(update=self._overrides)
        engine = Engine(
            effective,
            store=LanceVectorStore(uri=settings.lancedb_uri),
            embed_model=new_embedder(),
        )
        self.engines.append(engine)
        return engine


def under(path: str | Path, parent: Path) -> bool:
    """Return whether *path* resolves below *parent*."""
    return Path(path).resolve().is_relative_to(parent.resolve())
