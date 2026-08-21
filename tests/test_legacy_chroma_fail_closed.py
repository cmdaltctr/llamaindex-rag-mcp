"""TDD RED tests: recognised legacy Chroma data requires an explicit decision.

Spec source: openspec/changes/make-lancedb-default-and-isolate-chromadb
specs/lancedb-vector-store/spec.md — 'Recognised legacy Chroma data SHALL
require an explicit decision'.

The ``rag_mcp.core.vectordb.legacy`` module does not exist yet, so this
file is expected to FAIL (RED) at collection with ImportError until the
change lands. Do not create the module to make the collection pass — the
import error IS the red signal.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from rag_mcp.compose import ensure_runtime_setup, reset_runtime_setup
from rag_mcp.core.vectordb.legacy import (
    LegacyChromaDataError,
    classify_legacy_directory,
    evaluate_legacy_chroma_data,
)


def _make_sqlite_marker_dir(tmp_path: Path) -> Path:
    """Return a directory carrying the chroma.sqlite3 legacy marker."""
    directory = tmp_path / "legacy_chroma_sqlite"
    directory.mkdir()
    (directory / "chroma.sqlite3").write_text("sqlite-ish payload")
    return directory


def _make_segment_layout_dir(tmp_path: Path) -> Path:
    """Return a directory with the documented nested segment layout."""
    directory = tmp_path / "legacy_chroma_segments"
    (directory / "collection_a").mkdir(parents=True)
    (directory / "collection_a" / "segment.bin").write_bytes(b"\x00\x01")
    return directory


def _make_unrecognised_dir(tmp_path: Path) -> Path:
    """Return a non-empty directory without any recognised Chroma marker."""
    directory = tmp_path / "junk_dir"
    directory.mkdir()
    (directory / "random.txt").write_text("not chroma")
    return directory


def test_recognised_markers_sqlite(tmp_path: Path) -> None:
    """A chroma.sqlite3 file classifies the directory as recognised."""
    assert classify_legacy_directory(_make_sqlite_marker_dir(tmp_path)) == "recognised"


def test_recognised_markers_segment_layout(tmp_path: Path) -> None:
    """The nested segment layout classifies the directory as recognised."""
    layout = _make_segment_layout_dir(tmp_path)
    assert classify_legacy_directory(layout) == "recognised"


def test_empty_and_absent(tmp_path: Path) -> None:
    """A missing directory is 'absent'; an empty one is 'empty'."""
    assert classify_legacy_directory(tmp_path / "does_not_exist") == "absent"
    empty = tmp_path / "empty_dir"
    empty.mkdir()
    assert classify_legacy_directory(empty) == "empty"


def test_unrecognised_nonempty(tmp_path: Path) -> None:
    """A non-empty directory without markers is 'unrecognised_nonempty'."""
    junk = _make_unrecognised_dir(tmp_path)
    assert classify_legacy_directory(junk) == "unrecognised_nonempty"


def test_fail_closed_before_ingestion_or_retrieval(tmp_path: Path) -> None:
    """Recognised legacy data + default provenance stops startup, fully named.

    Spec: lancedb-vector-store, scenario 'Recognised legacy layout and no
    explicit backend' — the error names the directory, both explicit
    escape hatches, and discloses that no automatic migration happens.
    """
    legacy_dir = _make_sqlite_marker_dir(tmp_path)
    with pytest.raises(LegacyChromaDataError) as excinfo:
        evaluate_legacy_chroma_data(legacy_dir, "lancedb", "default")
    message = str(excinfo.value)
    assert str(legacy_dir) in message
    lowered = message.lower()
    assert ("re-ingest" in lowered) or ("re-ingestion" in lowered)
    assert "VECTOR_STORE=chroma" in message
    assert "VECTOR_STORE=lancedb" in message
    assert ("automatic migration" in message) or ("not migrated" in lowered)


def test_explicit_lancedb_passes_with_acknowledgement(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Explicit lancedb passes and logs a re-ingestion acknowledgement.

    Spec: lancedb-vector-store, scenario 'Explicit LanceDB acknowledges
    re-ingestion'.
    """
    legacy_dir = _make_sqlite_marker_dir(tmp_path)
    with caplog.at_level(logging.WARNING):
        evaluate_legacy_chroma_data(legacy_dir, "lancedb", "explicit")
    assert any(
        record.levelno >= logging.WARNING and "re-ingest" in record.getMessage().lower()
        for record in caplog.records
    )


def test_explicit_chroma_passes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Explicit chroma passes silently — the data matches the selected backend."""
    legacy_dir = _make_sqlite_marker_dir(tmp_path)
    with caplog.at_level(logging.WARNING):
        evaluate_legacy_chroma_data(legacy_dir, "chroma", "explicit")
    assert not any(
        record.levelno >= logging.WARNING and "re-ingest" in record.getMessage().lower()
        for record in caplog.records
    )


def test_unrecognised_nonempty_warns_not_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An unrecognised non-empty directory warns instead of failing startup.

    Spec: lancedb-vector-store, scenario 'Non-empty unrecognised
    directory'.
    """
    junk = _make_unrecognised_dir(tmp_path)
    with caplog.at_level(logging.WARNING):
        evaluate_legacy_chroma_data(junk, "lancedb", "default")
    assert any(record.levelno >= logging.WARNING for record in caplog.records)


@pytest.mark.parametrize(
    ("make_directory", "case_id"),
    [
        (_make_sqlite_marker_dir, "sqlite-marker"),
        (_make_segment_layout_dir, "segment-layout"),
    ],
)
def test_startup_wiring_reaches_cli_operator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_directory,
    case_id: str,
) -> None:
    """ensure_runtime_setup raises the operator-visible diagnostic, default only.

    Spec: lancedb-vector-store, scenario 'Recognised legacy layout and no
    explicit backend' — the fail-closed gate is wired into startup, so the
    exception text IS the operator-visible diagnostic surface. Only
    default provenance fails closed; explicit selections are covered by
    the evaluate_legacy_chroma_data tests above.
    """
    legacy_dir = make_directory(tmp_path)
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(legacy_dir))
    monkeypatch.setenv("LANCEDB_URI", str(tmp_path / "lancedb_store"))
    reset_runtime_setup()
    try:
        with pytest.raises(LegacyChromaDataError) as excinfo:
            ensure_runtime_setup()
        assert str(legacy_dir) in str(excinfo.value)
    finally:
        reset_runtime_setup()
