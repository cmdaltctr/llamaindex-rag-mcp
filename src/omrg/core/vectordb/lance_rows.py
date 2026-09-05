"""Arrow schema and row construction for precomputed upserts.

The upsert path builds a pyarrow table against the live table schema
before handing it to ``merge_insert``; these helpers own that
construction so ``lancedb.py`` stays inside the 500-line ceiling
(invariant #11), matching the sibling seam modules
(``lance_filter``/``lance_meta``/``lance_paged``).
"""

from __future__ import annotations

import pyarrow as pa

from .lance_meta import infer_arrow_type

__all__ = ["rows_to_arrow", "upsert_schema"]


def upsert_schema(dim: int, metadatas: list[dict]) -> pa.Schema:
    """Build the table schema for a first precomputed upsert.

    Mirrors the adapter's column layout (``id``, ``doc_id``, ``vector``,
    ``text``, ``metadata`` struct) with ``doc_id`` as a nullable string
    so later adapter writes cast cleanly into it.  Metadata field types
    use the shared inference rule (:func:`.lance_meta.infer_arrow_type`),
    so an all-null sample defaults to string instead of locking a
    ``pa.null()`` field that no later non-null write could satisfy.

    Args:
        dim: Vector dimension, fixed by the created table.
        metadatas: The batch's metadata dicts, sampled for inference.

    Returns:
        The Arrow schema for ``create_table``.
    """
    metadata_fields = dict.fromkeys(key for metadata in metadatas for key in metadata)
    struct_fields = [
        pa.field(key, infer_arrow_type([metadata.get(key) for metadata in metadatas]))
        for key in metadata_fields
    ]
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("doc_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
            pa.field("text", pa.string()),
            pa.field("metadata", pa.struct(struct_fields)),
        ]
    )


def rows_to_arrow(
    schema: pa.Schema,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: list[list[float]],
) -> pa.Table:
    """Build a pyarrow table aligned to *schema* from upsert rows.

    Columns absent from the upsert inputs (adapter internals such as
    ``doc_id``) are filled with nulls; null-typed columns are handled
    explicitly because ``pa.array`` cannot infer them from values.

    Args:
        schema: The live table schema to align against.
        ids: Row identifiers, one per row.
        documents: Row texts, one per row.
        metadatas: Row metadata dicts, one per row.
        embeddings: Caller-computed vectors, one per row.

    Returns:
        The pyarrow table for ``merge_insert``.
    """
    row_count = len(ids)
    columns: dict[str, pa.Array] = {}
    for field in schema:
        if field.name == "id":
            values: list[object] = list(ids)
        elif field.name == "text":
            values = list(documents)
        elif field.name == "metadata":
            values = [dict(metadata) for metadata in metadatas]
        elif field.name == "vector":
            values = [list(embedding) for embedding in embeddings]
        else:
            values = [None] * row_count
        if pa.types.is_null(field.type):
            columns[field.name] = pa.nulls(row_count, type=pa.null())
        else:
            columns[field.name] = pa.array(values, type=field.type)
    return pa.Table.from_pydict(columns, schema=schema)
