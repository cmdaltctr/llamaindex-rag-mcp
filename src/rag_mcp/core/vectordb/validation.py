"""Fail-closed structural validation for vector-store writes."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Sequence

from llama_index.core.schema import MetadataMode

from .identity import EmbeddingIdentity

__all__ = [
    "EmbeddingWriteContractError",
    "materialise_and_validate_node_embeddings",
    "validate_embedding_batch",
]


class EmbeddingWriteContractError(ValueError):
    """A vector batch violates the structural write contract."""


def validate_embedding_batch(
    identifiers: Sequence[str],
    vectors: Sequence[Sequence[object]],
    *,
    collection_name: str,
    embedding_identity: EmbeddingIdentity,
    existing_dimension: int | None = None,
) -> None:
    """Reject malformed vectors before a vector-store mutation.

    Args:
        identifiers: Stable node or row identifiers aligned with ``vectors``.
        vectors: Candidate embeddings to validate without modifying them.
        collection_name: Destination collection name for the diagnostic.
        embedding_identity: Provider and model diagnostic for the batch.
        existing_dimension: Established collection dimension, if present.

    Raises:
        EmbeddingWriteContractError: If the batch is structurally invalid.
    """
    context = (
        f"collection={collection_name!r}, provider={embedding_identity.provider!r}, "
        f"model={embedding_identity.model!r}"
    )
    if not identifiers or not vectors:
        raise EmbeddingWriteContractError(
            f"Invalid embedding batch for {context}: empty batch; "
            f"identifiers={list(identifiers)!r}, vector_count={len(vectors)}."
        )
    if len(identifiers) != len(vectors):
        surplus = list(range(len(identifiers), len(vectors)))
        raise EmbeddingWriteContractError(
            f"Invalid embedding batch for {context}: identifier/vector cardinality mismatch; "
            f"identifiers={list(identifiers)!r}, identifier_count={len(identifiers)}, "
            f"vector_count={len(vectors)}, surplus_vector_positions={surplus!r}."
        )

    dimensions: dict[int, list[str]] = {}
    failures: list[str] = []
    for position, (identifier, vector) in enumerate(zip(identifiers, vectors, strict=True)):
        try:
            dimension = len(vector)
        except TypeError:
            failures.append(f"identifier={identifier!r} at position {position} has no vector")
            continue
        if dimension == 0:
            failures.append(f"identifier={identifier!r} at position {position} has an empty vector")
            continue
        dimensions.setdefault(dimension, []).append(identifier)
        for element_position, value in enumerate(vector):
            if not isinstance(value, Real) or isinstance(value, bool):
                failures.append(
                    f"identifier={identifier!r} at position {position} has a non-numeric "
                    f"element at index {element_position}"
                )
                break
            if not math.isfinite(float(value)):
                failures.append(
                    f"identifier={identifier!r} at position {position} has a non-finite "
                    f"element at index {element_position}"
                )
                break

    if len(dimensions) > 1:
        observed = ", ".join(
            f"{dimension}: {identifiers!r}" for dimension, identifiers in sorted(dimensions.items())
        )
        failures.append(f"mixed vector dimensions ({observed})")
    if len(dimensions) == 1 and existing_dimension is not None:
        candidate_dimension = next(iter(dimensions))
        if candidate_dimension != existing_dimension:
            failures.append(
                f"candidate dimension {candidate_dimension} conflicts with existing collection "
                f"dimension {existing_dimension}; identifiers={list(identifiers)!r}"
            )
    if failures:
        raise EmbeddingWriteContractError(
            f"Invalid embedding batch for {context}: " + "; ".join(failures) + "."
        )


def materialise_and_validate_node_embeddings(
    nodes: list[Any],
    *,
    collection_name: str,
    embedding_identity: EmbeddingIdentity,
    existing_dimension: int | None,
    embed_model: Any,
) -> None:
    """Embed missing nodes, then validate the complete node batch.

    This is deliberately independent from every backend adapter. It only
    updates caller-owned nodes and performs no vector-store operation.
    """
    identifiers = [str(getattr(node, "node_id", index)) for index, node in enumerate(nodes)]
    missing = [
        (index, node)
        for index, node in enumerate(nodes)
        if getattr(node, "embedding", None) is None
    ]
    if missing:
        texts = [node.get_content(metadata_mode=MetadataMode.EMBED) for _, node in missing]
        embeddings = embed_model.get_text_embedding_batch(texts, show_progress=False)
        missing_ids = [identifiers[index] for index, _ in missing]
        validate_embedding_batch(
            missing_ids,
            embeddings,
            collection_name=collection_name,
            embedding_identity=embedding_identity,
            existing_dimension=existing_dimension,
        )
        for (_, node), embedding in zip(missing, embeddings, strict=True):
            node.embedding = list(embedding)

    vectors = [
        [] if getattr(node, "embedding", None) is None else getattr(node, "embedding")
        for node in nodes
    ]
    validate_embedding_batch(
        identifiers,
        vectors,
        collection_name=collection_name,
        embedding_identity=embedding_identity,
        existing_dimension=existing_dimension,
    )
