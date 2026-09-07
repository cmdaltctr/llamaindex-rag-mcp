"""Red-first coverage for OpenSpec tasks 2.11 and 2.12.

OCR routing diagnostics are parser telemetry. They stay stored and retrievable,
but never form part of EMBED or LLM text.
"""

from __future__ import annotations

import pytest
from llama_index.core.schema import MetadataMode, TextNode

from omrg.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS, stamp_source_lineage

OCR_DIAGNOSTIC_KEYS = (
    "ocr_required",
    "ocr_used",
    "ocr_backend",
    "pages_needing_ocr",
)


@pytest.mark.parametrize(
    ("label", "diagnostics"),
    [
        (
            "fast",
            {
                "ocr_required": False,
                "ocr_used": False,
                "ocr_backend": "pdf-inspector-fast",
                "pages_needing_ocr": 0,
            },
        ),
        (
            "fallback",
            {
                "ocr_required": True,
                "ocr_used": True,
                "ocr_backend": "paddleocr-fallback",
                "pages_needing_ocr": 2,
            },
        ),
        (
            "degraded",
            {
                "ocr_required": True,
                "ocr_used": False,
                "ocr_backend": "ocr-unavailable",
                "pages_needing_ocr": 2,
            },
        ),
    ],
)
def test_ocr_diagnostics_are_excluded_from_embed_and_llm_text(
    label: str, diagnostics: dict[str, str | int | bool]
) -> None:
    """Tasks 2.11-2.12: every branch hides telemetry from model-facing text."""
    node = TextNode(
        text="The specialised parser extracted this evidence.", metadata=dict(diagnostics)
    )
    stamp_source_lineage(
        [node],
        file_path=f"/fixtures/{label}.pdf",
        source_id=f"src-{label}",
        content_hash="a" * 64,
        index_identity="b" * 64,
        source_version="c" * 64,
        source_attempt="attempt-1",
    )

    assert set(OCR_DIAGNOSTIC_KEYS).issubset(EXCLUDED_EMBED_METADATA_KEYS)
    assert {key: node.metadata[key] for key in OCR_DIAGNOSTIC_KEYS} == diagnostics
    for mode in (MetadataMode.EMBED, MetadataMode.LLM):
        model_text = node.get_content(metadata_mode=mode)
        assert node.text in model_text
        for key in OCR_DIAGNOSTIC_KEYS:
            assert f"{key}:" not in model_text
        assert str(diagnostics["ocr_backend"]) not in model_text


class _StoredDiagnosticRow:
    """Small vector-store double for retrieval metadata adaptation."""

    def __init__(self, metadata: dict[str, str | int | bool]) -> None:
        self.metadata = metadata

    def query_dense(self, **_kwargs):
        return [
            {
                "id": "row-1",
                "score": 1.0,
                "score_kind": "dense_similarity",
                "document": "stored chunk text",
                "metadata": self.metadata,
            }
        ]


class _UnitEmbedding:
    """Avoid the global embedder in retrieval-row contract tests."""

    model_name = "ocr-diagnostic-test"

    @staticmethod
    def get_query_embedding(_query: str) -> list[float]:
        return [1.0]


@pytest.mark.parametrize(
    ("label", "diagnostics"),
    [
        (
            "fast",
            {
                "ocr_required": False,
                "ocr_used": False,
                "ocr_backend": "pdf-inspector-fast",
                "pages_needing_ocr": 0,
            },
        ),
        (
            "fallback",
            {
                "ocr_required": True,
                "ocr_used": True,
                "ocr_backend": "paddleocr-fallback",
                "pages_needing_ocr": 2,
            },
        ),
        (
            "degraded",
            {
                "ocr_required": True,
                "ocr_used": False,
                "ocr_backend": "ocr-unavailable",
                "pages_needing_ocr": 2,
            },
        ),
    ],
)
def test_ocr_diagnostics_remain_stored_and_retrievable(
    label: str, diagnostics: dict[str, str | int | bool]
) -> None:
    """Task 2.12: each extraction state is visible in retrieval metadata."""
    from omrg.core.retrieval.dense import _dense_query_rows

    metadata = {"file_path": f"/fixtures/{label}.pdf", **diagnostics}
    rows = _dense_query_rows(
        _StoredDiagnosticRow(metadata),
        "documents",
        "evidence",
        1,
        embed_model=_UnitEmbedding(),
    )

    assert rows[0]["metadata"] == metadata
    assert rows[0]["source"] == metadata["file_path"]
    assert rows[0]["metadata"]["pages_needing_ocr"] == diagnostics["pages_needing_ocr"]
    assert isinstance(rows[0]["metadata"]["pages_needing_ocr"], int)
