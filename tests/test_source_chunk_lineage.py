"""Red-first contract tests for stable source/chunk lineage.

Pins ``openspec/changes/add-stable-source-chunk-lineage`` tasks 1.1-1.4 before
the implementation exists:

- deterministic ``source_id`` (canonical path) and ``chunk_id`` (stored text
  within one source version) formulas with pinned digests;
- lineage stamping: one shared ``SOURCE`` relationship, ordered chunk
  membership, and exclusion of every machine key from model-facing text;
- the pre-mutation incompatibility guard for pre-lineage rows.

Store-bound coverage (replacement, persistence, lifecycle) lives in
``tests/test_lineage_store_contract.py``; retrieval propagation in
``tests/test_lineage_retrieval.py``; the clean-boundary regression in the
rewritten ``tests/test_ingestion_stage3_legacy.py``.

New ``source_state`` helpers are imported lazily inside tests (the established
red-first pattern from ``tests/test_embedding_write_contract.py``) so the file
collects cleanly and every scenario reports its own failure before the
implementation lands.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest
from llama_index.core.schema import MetadataMode, NodeRelationship, RelatedNodeInfo, TextNode

from omrg.core.ingestion.hashing import sha256_file
from omrg.core.vectordb import get_default_store

_COLLECTION = "lineage_core"


# ── Spec-pinned formulas (computed independently of the implementation) ──


def _expected_source_id(canonical_file_path: str) -> str:
    """Return the spec-pinned source_id digest for one canonical path."""
    return "src_" + hashlib.sha256(("file\0" + canonical_file_path).encode("utf-8")).hexdigest()


def _expected_chunk_id(source_id: str, source_version: str, index: int, text: str) -> str:
    """Return the spec-pinned chunk_id digest for one stored chunk."""
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return (
        "chk_"
        + hashlib.sha256(
            (source_id + "\0" + source_version + "\0" + str(index) + "\0" + text_hash).encode(
                "utf-8"
            )
        ).hexdigest()
    )


def _expected_row_id(source_id: str, source_attempt: str, chunk_id: str) -> str:
    """Return the spec-pinned attempt-specific vector-row id."""
    return hashlib.sha256(
        (source_id + "\0" + source_attempt + "\0" + chunk_id).encode("utf-8")
    ).hexdigest()


def _source_state():
    """Import the source-state module lazily (red-first, see module docstring)."""
    from omrg.core.ingestion import source_state

    return source_state


# ── Task 1.1: the deterministic source_id formula ────────────────────────


class TestSourceIdentities:
    """The canonical-path source identity and its scoped filters."""

    def test_pins_exact_formula_and_digest_shape(self, tmp_path: Path) -> None:
        """Spec: source_id is src_ + SHA-256('file\0' + canonical path)."""
        source = tmp_path / "formula.txt"
        source.write_text("ignored", encoding="utf-8")
        ss = _source_state()
        canonical = ss.canonical_source_path(str(source))

        assert canonical == str(Path(str(source)).expanduser().resolve())
        assert ss.build_source_id(canonical) == _expected_source_id(canonical)
        derived = ss.build_source_id(canonical)
        assert derived.startswith("src_")
        assert len(derived) == len("src_") + 64
        assert derived == derived.lower()

    def test_same_canonical_path_is_stable_across_request_forms(self, tmp_path: Path) -> None:
        """Spec: one canonical path is one identity; redundant spellings collapse."""
        ss = _source_state()
        source = tmp_path / "stable.txt"
        source.write_text("content", encoding="utf-8")
        canonical = ss.canonical_source_path(str(source))

        # Redundant ``..`` segments and a Path object resolve to the same
        # canonical absolute path (``"./" + absolute`` would be a relative
        # path rooted at the process CWD, which is a different file).
        dotted = str(tmp_path / ".." / tmp_path.name / "stable.txt")
        assert ss.canonical_source_path(dotted) == canonical
        assert ss.canonical_source_path(source) == canonical
        assert ss.build_source_id(canonical) == ss.build_source_id(canonical)

    def test_equal_bytes_at_different_paths_remain_distinct_sources(self, tmp_path: Path) -> None:
        """Spec: equal bytes share source_content_hash but differ in source_id."""
        payload = "identical bytes for two logical sources"
        first = tmp_path / "first.txt"
        second = tmp_path / "second.txt"
        first.write_text(payload, encoding="utf-8")
        second.write_text(payload, encoding="utf-8")
        ss = _source_state()

        assert sha256_file(first) == sha256_file(second)
        sid_first = ss.build_source_id(ss.canonical_source_path(str(first)))
        sid_second = ss.build_source_id(ss.canonical_source_path(str(second)))
        assert sid_first != sid_second

    def test_formula_is_collection_independent(self) -> None:
        """Spec: the collection name does not participate in the formula."""
        ss = _source_state()
        assert set(inspect.signature(ss.build_source_id).parameters) == {"canonical_file_path"}

    def test_source_scoped_filter_shapes(self) -> None:
        """Filters select rows by source_id instead of file_path."""
        ss = _source_state()
        assert ss.source_where("src_abc") == {"source_id": "src_abc"}
        assert ss.source_version_where(
            "src_abc",
            content_hash="hash",
            index_identity="identity",
            source_version="version",
        ) == {
            "$and": [
                {"source_id": "src_abc"},
                {"source_content_hash": "hash"},
                {"source_index_identity": "identity"},
                {"source_version": "version"},
            ]
        }
        assert ss.source_attempt_where("src_abc", "attempt-1") == {
            "$and": [
                {"source_id": "src_abc"},
                {"source_attempt": "attempt-1"},
            ]
        }


# ── Task 1.2: the deterministic chunk_id formula ─────────────────────────


class TestChunkIdentities:
    """Chunk identity within one source version."""

    _SOURCE_ID = "src_" + "a" * 64
    _SOURCE_VERSION = "v" * 64
    _TEXT = "one stored chunk of text"

    def test_pins_exact_formula_and_digest_shape(self) -> None:
        """Spec: chk_ + SHA-256(source_id NUL version NUL index NUL text hash)."""
        ss = _source_state()
        chunk_id = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=3,
            text=self._TEXT,
        )
        assert chunk_id == _expected_chunk_id(self._SOURCE_ID, self._SOURCE_VERSION, 3, self._TEXT)
        assert chunk_id.startswith("chk_")
        assert len(chunk_id) == len("chk_") + 64
        assert chunk_id == chunk_id.lower()

    def test_identical_inputs_are_stable(self) -> None:
        """Spec: forced re-ingestion reproduces stable chunk identities."""
        ss = _source_state()
        kwargs = dict(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=0,
            text=self._TEXT,
        )
        assert ss.build_chunk_id(**kwargs) == ss.build_chunk_id(**kwargs)

    def test_changed_text_or_version_changes_identity(self) -> None:
        """Spec: changed chunk text or source version changes the chunk id."""
        ss = _source_state()
        base = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=0,
            text=self._TEXT,
        )
        changed_text = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=0,
            text=self._TEXT + " edited",
        )
        changed_version = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version="w" * 64,
            chunk_index=0,
            text=self._TEXT,
        )
        assert changed_text != base
        assert changed_version != base

    def test_repeated_equal_text_at_different_indices_is_distinct(self) -> None:
        """Spec: the zero-based decimal ordinal distinguishes repeated text."""
        ss = _source_state()
        first = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=0,
            text=self._TEXT,
        )
        repeat = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=1,
            text=self._TEXT,
        )
        tenth = ss.build_chunk_id(
            source_id=self._SOURCE_ID,
            source_version=self._SOURCE_VERSION,
            chunk_index=10,
            text=self._TEXT,
        )
        assert repeat != first
        assert tenth != first
        assert tenth == _expected_chunk_id(self._SOURCE_ID, self._SOURCE_VERSION, 10, self._TEXT)


# ── Tasks 1.3 + 1.4: lineage stamping and model-text exclusion ───────────

_LINEAGE_KEYS = (
    "source_id",
    "chunk_id",
    "source_content_hash",
    "source_index_identity",
    "source_version",
    "source_attempt",
    "source_chunk_count",
    "source_chunk_index",
)


def _five_nodes(file_path: str) -> list[TextNode]:
    """Build five plain nodes carrying ordinary reader-style metadata."""
    return [
        TextNode(
            text=f"chunk number {position} text",
            metadata={"file_path": file_path, "file_name": Path(file_path).name},
        )
        for position in range(5)
    ]


class TestLineageStamping:
    """Task 1.3: one shared SOURCE relationship and ordered membership."""

    def test_five_chunks_share_one_source_and_ordered_identity(self, tmp_path: Path) -> None:
        """Spec: five chunks share one source relationship and one ordered set."""
        ss = _source_state()
        file_path = str(tmp_path / "five.txt")
        source_id = _expected_source_id(ss.canonical_source_path(file_path))
        nodes = _five_nodes(file_path)

        ss.stamp_source_lineage(
            nodes,
            file_path=file_path,
            source_id=source_id,
            content_hash="c" * 64,
            index_identity="i" * 64,
            source_version="v" * 64,
            source_attempt="attempt-1",
        )

        assert len({node.metadata["chunk_id"] for node in nodes}) == 5
        assert sorted(node.metadata["source_chunk_index"] for node in nodes) == list(range(5))
        for position, node in enumerate(nodes):
            assert node.relationships[NodeRelationship.SOURCE].node_id == source_id
            assert node.metadata["file_path"] == file_path
            assert node.metadata["source_id"] == source_id
            assert node.metadata["source_chunk_count"] == 5
            assert node.metadata["source_chunk_index"] == position
            assert node.metadata["chunk_id"] == _expected_chunk_id(
                source_id, "v" * 64, position, node.get_content(metadata_mode=MetadataMode.NONE)
            )
            for key in _LINEAGE_KEYS:
                assert key in node.metadata
        for node in nodes:
            assert node.id_ == _expected_row_id(
                source_id, node.metadata["source_attempt"], node.metadata["chunk_id"]
            )


class TestMetadataExclusions:
    """Lineage stamping keeps machine keys out of model text.

    Updated by fix-embedding-and-structure-fidelity-1: stamping no longer
    leaves model text byte-identical — it is the single owner of the
    embedding-text exclusion contract (design D1), so it now also removes
    the declared noise keys (``file_path`` and siblings) and restores the
    retained keys (``file_name``, design D2) that the LlamaIndex reader
    default excludes. What must never change: lineage keys stay out of
    model text, and the chunk's own text survives stamping.
    """

    def test_stamping_keeps_lineage_out_and_applies_declared_exclusions(
        self, tmp_path: Path
    ) -> None:
        """Spec: lineage stays in metadata; declared noise drops; file_name stays."""
        ss = _source_state()
        file_path = str(tmp_path / "excluded.txt")
        nodes = _five_nodes(file_path)[:1]
        node = nodes[0]

        ss.stamp_source_lineage(
            nodes,
            file_path=file_path,
            source_id="src_" + "b" * 64,
            content_hash="c" * 64,
            index_identity="i" * 64,
            source_version="v" * 64,
            source_attempt="attempt-9",
        )

        embed_after = node.get_content(metadata_mode=MetadataMode.EMBED)
        llm_after = node.get_content(metadata_mode=MetadataMode.LLM)
        for key in _LINEAGE_KEYS:
            assert key in node.metadata
        # The chunk's own text survives stamping in both modes.
        assert "chunk number 0 text" in embed_after
        assert "chunk number 0 text" in llm_after
        # The rendered lineage field must be absent. A bare value check is
        # not meaningful for short values such as a single-digit chunk
        # index, which can appear inside the fixture path itself.
        for text in (embed_after, llm_after):
            for key in _LINEAGE_KEYS:
                assert f"{key}:" not in text
        # Distinctive long values (prefixed ids, 64-char digests, the
        # attempt token) must not leak into model-visible content either.
        for key in _LINEAGE_KEYS:
            value = str(node.metadata[key])
            if len(value) >= 8:
                assert value not in embed_after
                assert value not in llm_after
        # Declared filesystem bookkeeping drops out of model text...
        for text in (embed_after, llm_after):
            assert "file_path:" not in text
        # ...while file_name is retained (design D2 inverts the LlamaIndex
        # default that excludes file_name and keeps file_path).
        assert "file_name: excluded.txt" in embed_after
        assert "file_name: excluded.txt" in llm_after


# ── The pre-mutation incompatibility guard ───────────────────────────────


class TestCompatibilityGuard:
    """Unexpected pre-lineage rows fail with a rebuild instruction, no mutation."""

    def _guard(self):
        """Return the guard callable (lazy import, see module docstring)."""
        return _source_state().assert_source_lineage_compatible

    def _seed_row(self, store, file_path: str, text: str, extra_metadata: dict) -> None:
        """Seed one production-shaped row, optionally with disagreeing lineage."""
        node = TextNode(
            text=text,
            metadata={"file_path": file_path, **extra_metadata},
            relationships={
                NodeRelationship.SOURCE: RelatedNodeInfo(
                    node_id="00000000-0000-0000-0000-000000000000"
                )
            },
        )
        store.write_nodes([node], _COLLECTION)

    def test_absent_collection_is_a_no_op(self) -> None:
        """Spec: an absent collection needs no rebuild."""
        self._guard()(
            get_default_store(),
            "lineage_never_created",
            file_path="/tmp/absent.txt",
            source_id="src_x",
        )

    def test_path_without_rows_is_a_no_op(self, tmp_path: Path) -> None:
        """Spec: zero rows for the path need no rebuild."""
        store = get_default_store()
        self._seed_row(store, str(tmp_path / "other.txt"), "unrelated row", {})
        self._guard()(
            store,
            _COLLECTION,
            file_path=str(tmp_path / "never-ingested.txt"),
            source_id="src_x",
        )

    @pytest.mark.parametrize(
        "extra_metadata",
        [{}, {"source_id": "src_" + "f" * 64}],
        ids=["missing-source-id", "disagreeing-source-id"],
    )
    def test_incompatible_rows_raise_with_rebuild_instruction(
        self, tmp_path: Path, extra_metadata: dict
    ) -> None:
        """Spec: missing or disagreeing source_id raises; stored rows stay put."""
        guard = self._guard()
        store = get_default_store()
        file_path = str(tmp_path / "guarded.txt")
        self._seed_row(store, file_path, "legacy searchable sentinel", extra_metadata)

        with pytest.raises(RuntimeError) as excinfo:
            guard(
                store,
                _COLLECTION,
                file_path=file_path,
                source_id=_expected_source_id(file_path),
            )
        assert "rebuild" in str(excinfo.value).lower()
        assert store.count_where(_COLLECTION, {"file_path": file_path}) == 1
