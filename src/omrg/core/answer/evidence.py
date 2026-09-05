"""Evidence assembly for grounded answering.

Shared by the core pipeline and the MCP transport's MRTR resolvers so
both paths build identical evidence rows and labelled nodes by
construction rather than by duplication (design D6: core owns evidence
numbering).  Split from ``pipeline.py`` when the claim-verification
stage (ADR-059) needed head-room under the 500-line ceiling.
"""

from __future__ import annotations

from llama_index.core.schema import NodeWithScore, TextNode

#: Lineage fields carried on every evidence row.  Same lineage as
#: ``retriever._LINEAGE_FIELDS`` minus ``chunk_ids``, which each row
#: carries normalised (representative chunk first) via the logic below.
_EVIDENCE_FIELDS = (
    "chunk_id",
    "source_id",
    "source_version",
    "source",
    "source_chunk_index",
    "score",
    "score_kind",
)


def _evidence_rows(rows: list[dict]) -> list[dict]:
    """Normalise search rows to evidence rows with merged constituents.

    Each row carries the pinned lineage fields, its 1-based ``ordinal``
    (the supplied-source number citations refer to) and the chunk text.
    ``chunk_ids`` lists every constituent chunk of a merged assembly row
    (the merged row's representative included); rows that were not
    merged carry a single-element list.
    """
    evidence: list[dict] = []
    for ordinal, row in enumerate(rows, start=1):
        entry: dict = {field: row.get(field) for field in _EVIDENCE_FIELDS}
        entry["ordinal"] = ordinal
        chunk_ids = [cid for cid in row.get("chunk_ids") or [] if cid is not None]
        if row.get("chunk_id") is not None and row["chunk_id"] not in chunk_ids:
            chunk_ids.insert(0, row["chunk_id"])
        entry["chunk_ids"] = chunk_ids
        entry["text"] = row.get("text") or ""
        evidence.append(entry)
    return evidence


def _labelled_nodes(evidence: list[dict]) -> list[NodeWithScore]:
    """Build scored nodes whose texts carry the ``[n]`` source labels."""
    nodes: list[NodeWithScore] = []
    for ordinal, row in enumerate(evidence, start=1):
        metadata = {field: row.get(field) for field in _EVIDENCE_FIELDS}
        metadata["chunk_ids"] = list(row.get("chunk_ids") or [])
        node = TextNode(text=f"[{ordinal}]\n{row['text']}", metadata=metadata)
        score = row.get("score")
        nodes.append(NodeWithScore(node=node, score=float(score) if score is not None else None))
    return nodes


# ── Transport-planning aliases ────────────────────────────────────────────
# The MCP transport's MRTR resolvers share these pure helpers with the
# pipeline so both paths agree by construction rather than by duplication.


def evidence_rows(rows: list[dict]) -> list[dict]:
    """Public alias of :func:`_evidence_rows` for transport resolvers."""
    return _evidence_rows(rows)


def labelled_nodes(evidence: list[dict]) -> list[NodeWithScore]:
    """Public alias of :func:`_labelled_nodes` for transport resolvers."""
    return _labelled_nodes(evidence)
