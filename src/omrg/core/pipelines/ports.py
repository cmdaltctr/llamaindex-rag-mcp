"""Typed port contracts for graph operations.

A port type says what a value is (its :class:`PortKind`) and which
guarantees travel with it: source and collection provenance, the score
kinds a ranked list may carry, whether the value is bound to an embedding
identity, and which reader declarations a document set keeps. An output
port type lists what the producer guarantees. An input port type lists what
the consumer requires. :func:`check_port_compatibility` compares the two.

The score-kind strings equal the constants the retrieval and vector-store
domains emit. This package must not import those domains, so a unit test
pins the equality instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Score kinds emitted by existing domain code (pinned by a unit test).
SCORE_KIND_DENSE = "dense_similarity_v1"
SCORE_KIND_NATIVE_SPARSE = "native_fts_v1"
SCORE_KIND_RRF = "rrf_v1"
SCORE_KIND_RERANK = "reranker_sigmoid_v1"
#: Sparse branch rows carry rank order only (no score field), so no
#: threshold may read them as a score. Covers native and BM25 runners.
SCORE_KIND_SPARSE_RANK = "sparse_rank_v1"

# Reader declarations carried by ``BackendRead`` in the ingestion domain.
READER_TEXT_FORMAT = "text_format"
READER_STRUCTURED = "structured"


class PortKind(StrEnum):
    """What a port value is."""

    SOURCES = "sources"
    DOCUMENTS = "documents"
    CHUNKS = "chunks"
    EMBEDDED_CHUNKS = "embedded_chunks"
    COMMIT_SUMMARY = "commit_summary"
    QUERY = "query"
    QUERY_VECTOR = "query_vector"
    RANKED_EVIDENCE = "ranked_evidence"
    CONTEXT = "context"
    ANSWER = "answer"


class Provenance(StrEnum):
    """Provenance guarantees a value can carry."""

    SOURCE = "source"
    COLLECTION = "collection"
    CHUNK_LINEAGE = "chunk_lineage"


class Cardinality(StrEnum):
    """How many connections an input port accepts.

    ``ONE`` needs exactly one connection. ``OPTIONAL`` accepts zero or one.
    ``MANY`` needs one or more; the adapter receives a tuple in edge
    declaration order, never in completion order.
    """

    ONE = "one"
    OPTIONAL = "optional"
    MANY = "many"


@dataclass(frozen=True)
class PortType:
    """The static contract of a port.

    Attributes:
        kind: What the value is.
        provenance: Provenance guaranteed (output) or required (input).
        score_kinds: For ranked values, the score kinds a producer may
            emit, or the score kinds a consumer accepts. ``None`` on an
            output means "not declared"; ``None`` on an input means "any".
        embedding_identity: Output: the value is bound to the host
            embedding identity. Input: the consumer needs that binding.
        reader_declarations: Reader declarations kept (output) or needed
            (input), for example ``text_format``.
    """

    kind: PortKind
    provenance: frozenset[Provenance] = field(default_factory=frozenset)
    score_kinds: frozenset[str] | None = None
    embedding_identity: bool = False
    reader_declarations: frozenset[str] = field(default_factory=frozenset)

    def to_schema(self) -> dict[str, Any]:
        """Return a JSON-safe description with sorted sets."""
        return {
            "kind": self.kind.value,
            "provenance": sorted(p.value for p in self.provenance),
            "score_kinds": None if self.score_kinds is None else sorted(self.score_kinds),
            "embedding_identity": self.embedding_identity,
            "reader_declarations": sorted(self.reader_declarations),
        }


@dataclass(frozen=True)
class PortSpec:
    """A named port on an operation.

    Attributes:
        name: Port name, unique per direction on one operation.
        type: The port contract.
        cardinality: Connections accepted (input ports only).
        description: Short help text for clients.
    """

    name: str
    type: PortType
    cardinality: Cardinality = Cardinality.ONE
    description: str = ""

    @property
    def required(self) -> bool:
        """Return whether the port needs at least one connection."""
        return self.cardinality is not Cardinality.OPTIONAL

    def to_schema(self) -> dict[str, Any]:
        """Return a JSON-safe description."""
        return {
            "name": self.name,
            "type": self.type.to_schema(),
            "cardinality": self.cardinality.value,
            "description": self.description,
        }


@dataclass(frozen=True)
class EmbeddingRef:
    """The embedding identity that owns a vector space.

    Dimensions are informative only: two models with equal dimensions are
    still different identities.

    Attributes:
        provider: Effective embedding backend name.
        model: Embedding model identifier.
        dimensions: Vector dimension, when known.
    """

    provider: str
    model: str
    dimensions: int | None = None

    def same_space(self, other: EmbeddingRef) -> bool:
        """Return whether both refer to the same provider and model."""
        return (self.provider, self.model) == (other.provider, other.model)

    def label(self) -> str:
        """Return ``provider/model`` with dimensions when known."""
        dims = f", {self.dimensions} dimensions" if self.dimensions is not None else ""
        return f"{self.provider}/{self.model}{dims}"


@dataclass(frozen=True)
class PayloadProvenance:
    """Runtime provenance an adapter attaches to a port value.

    Adapters may use this carrier so downstream nodes and run records see
    the same guarantees the static port type promised.

    Attributes:
        collection: Collection the value came from or targets.
        source_ids: Canonical source identities involved.
        score_kind: Score kind of a ranked value.
        embedding: Embedding identity of a vector-bound value.
        reader: Reader declarations, for example ``{"text_format": "markdown"}``.
    """

    collection: str | None = None
    source_ids: tuple[str, ...] = ()
    score_kind: str | None = None
    embedding: EmbeddingRef | None = None
    reader: tuple[tuple[str, str], ...] = ()


def check_port_compatibility(produced: PortType, required: PortType) -> list[str]:
    """Compare a producer's guarantees with a consumer's requirements.

    Args:
        produced: Output port type (guarantees).
        required: Input port type (requirements).

    Returns:
        Plain-English reasons the connection is invalid. Empty when valid.
    """
    if produced.kind is not required.kind:
        return [f"'{produced.kind.value}' cannot connect to '{required.kind.value}'"]
    reasons: list[str] = []
    missing = sorted(p.value for p in required.provenance - produced.provenance)
    if missing:
        reasons.append(f"value does not carry required provenance: {', '.join(missing)}")
    if required.score_kinds is not None:
        if produced.score_kinds is None:
            reasons.append(
                "producer does not declare its score kind; consumer accepts only "
                f"{', '.join(sorted(required.score_kinds))}"
            )
        else:
            extra = sorted(produced.score_kinds - required.score_kinds)
            if extra:
                reasons.append(
                    f"score kind {', '.join(extra)} is not accepted; consumer accepts only "
                    f"{', '.join(sorted(required.score_kinds))}"
                )
    if required.embedding_identity and not produced.embedding_identity:
        reasons.append("consumer needs a value bound to the embedding identity")
    missing_decl = sorted(required.reader_declarations - produced.reader_declarations)
    if missing_decl:
        reasons.append(f"reader declarations are not preserved: {', '.join(missing_decl)}")
    return reasons
