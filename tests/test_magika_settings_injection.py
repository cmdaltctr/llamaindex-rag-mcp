"""Regression tests: content-type detection uses injected settings.

Found during Experiment 31: the ingestion pipeline called
``detect_file_types(path)`` without the ``EffectiveSettings`` it already
held, so the Magika availability check resolved the process-global
default (``integrations/magika.py:_magika_binary``) and raised in any
process that constructed an ``Engine`` directly — silently degrading
every file to extension-based routing. See
``openspec/changes/thread-settings-through-magika-detection/``.
"""

from __future__ import annotations

import logging
import math
import types
from pathlib import Path

import pytest
from llama_index.core.embeddings import MockEmbedding

from omrg.core.ingestion import ingest_path_async
from omrg.core.settings import EffectiveSettings, EmbeddingBlock, MetadataBlock
from omrg.core.vectordb.lancedb import LanceVectorStore


class _UnitNormMockEmbedding(MockEmbedding):
    """Constant-vector mock that satisfies the unit-norm embedding guard."""

    def _get_vector(self) -> list[float]:
        vector = super()._get_vector()
        norm = math.sqrt(math.fsum(x * x for x in vector))
        return [x / norm for x in vector] if norm else list(vector)


@pytest.mark.asyncio
async def test_ingest_content_type_detection_needs_no_global_settings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Ingestion with injected settings MUST NOT hit the settings-lookup fallback.

    Reproduces the direct-Engine condition: no process-global default
    installed (the shared conftest installs one for every test, so this
    test resets it). Content-type detection must then either run Magika
    or emit the documented "CLI not installed" degradation — never the
    "Magika detection failed ... No default EffectiveSettings installed"
    catch.
    """
    from omrg.core.settings import reset_default_effective_settings

    reset_default_effective_settings()

    source = tmp_path / "probe.md"
    source.write_text("# Probe\n\nMagika settings-injection probe text.\n" * 30, encoding="utf-8")
    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        # Empty tokenizer identity forces the legacy splitter path, so the
        # test never touches the Hugging Face cache.
        embedding=EmbeddingBlock(tokenizer_model="", tokenizer_revision=""),
    )
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))

    with caplog.at_level(logging.DEBUG, logger="omrg.core"):
        result = await ingest_path_async(
            str(source),
            collection_name="magika_settings_injection",
            effective_settings=settings,
            store=store,
            embed_model=_UnitNormMockEmbedding(embed_dim=8),
        )

    assert result["status"] == "ok", result

    settings_failures = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("Magika detection failed")
    ]
    assert not settings_failures, (
        "content-type detection degraded to extension routing inside "
        f"ingest_path_async: {settings_failures}"
    )

    # Detection must have genuinely resolved — either a live Magika scan
    # (debug) or the documented unavailable-binary degradation.
    resolved = [
        record.getMessage()
        for record in caplog.records
        if "Magika detected" in record.getMessage()
        or "Magika CLI not installed" in record.getMessage()
    ]
    assert resolved, "detection produced neither a scan nor the documented fallback"


def test_magika_binary_reads_injected_settings_not_the_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_magika_binary(settings=...)`` MUST use the injected value only.

    A raising stub on the module's global getter proves the global is
    never consulted when settings are injected.
    """
    from omrg.integrations import magika as magika_module

    def _raise() -> None:
        raise RuntimeError("global settings read attempted")

    monkeypatch.setattr(magika_module, "get_default_effective_settings", _raise)
    stub = types.SimpleNamespace(magika_binary="injected-magika-probe")
    assert magika_module._magika_binary(settings=stub) == "injected-magika-probe"
