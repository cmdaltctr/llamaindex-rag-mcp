"""Context assembly — the retrieval stage between ranking and return.

Implements the ``retrieval-context-assembly`` capability of the change
``fix-retrieval-freshness-and-context-assembly-2``.  Assembly is the
single place returned evidence is reshaped: adjacent chunks of one
source version are merged so splitter-produced overlap text is not
returned twice, and a caller may request bounded neighbour expansion.
The stage never re-ranks, never re-scores and never drops evidence
(design decisions D3 and D4).

Merging is contiguity-driven, not similarity-driven: only chunks that
are adjacent in the same ``(source_id, source_version)`` merge, and the
merge removes only a longest exact suffix/prefix text match whose
tokenised size fits the configured ``chunking.chunk_overlap`` budget.
When no exact match fits, the texts are concatenated without deletion,
so unique text is never lost and no character boundary is ever inferred
from the numeric token budget.

Neighbour expansion is opt-in (``expand_window`` of zero, the default,
adds nothing) and reads through the lineage navigator's store-neutral
filtered row-read contract, so the collection is never scanned.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from ..vectordb.base import VectorStore
from .lineage import neighbours

__all__ = [
    "ASSEMBLY_INTERNAL_FIELDS",
    "MERGED_CHUNK_IDS_KEY",
    "assemble",
    "promote_assembly_diagnostics",
]

logger = logging.getLogger(__name__)

# Public additive key carried by merged rows: the ``chunk_id`` of every
# constituent chunk, in ascending ``source_chunk_index`` order.  Rows that
# were not merged keep the plain ``chunk_id`` key and gain nothing.
MERGED_CHUNK_IDS_KEY = "chunk_ids"

# Assembly-internal marker keys.  They are attached to every row produced
# by :func:`assemble` so diagnostics can report what the stage did, and
# they are stripped from public results by
# ``_strip_internal_result_fields`` (task 5.9) exactly like the other
# internal fields.
ASSEMBLY_INTERNAL_FIELDS = (
    "_assembly_merged",
    "_assembly_chunk_count",
    "_assembly_expanded",
)

# Separator used by the border search.  A NUL byte cannot occur in chunk
# text (readers strip it), which keeps the computed borders honest.
_BORDER_SENTINEL = "\x00"


def _field(row: Mapping[str, Any], key: str) -> Any:
    """Return one lineage field from a result row.

    Reads the stable top-level lineage keys first (retrieval result rows
    and lineage neighbour rows both carry them) and falls back to the
    row's nested ``metadata`` mapping for bare store-shaped rows.

    Args:
        row: A retrieval result row or a metadata mapping.
        key: The lineage metadata key to read.

    Returns:
        The value, or ``None`` when absent on both levels.
    """
    if key in row:
        return row[key]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _is_int(value: Any) -> bool:
    """Return whether *value* is an integer and not a boolean in disguise."""
    return isinstance(value, int) and not isinstance(value, bool)


def _lineage_unit_key(row: Mapping[str, Any]) -> tuple[str, str, int] | None:
    """Return the contiguity key of one row, or ``None`` when inert.

    The key is ``(source_id, source_version, source_chunk_index)`` — the
    same identity adjacency is keyed on, so chunks from two versions of
    one document never merge.  Rows without usable lineage (experiment
    precomputed rows) are inert and pass through untouched.
    """
    source_id = _field(row, "source_id")
    source_version = _field(row, "source_version")
    index = _field(row, "source_chunk_index")
    if source_id is None or source_version is None or not _is_int(index) or index < 0:
        return None
    return str(source_id), str(source_version), index


def _positive_int(value: Any) -> int:
    """Return *value* as a positive int, or zero when it is unusable."""
    return value if _is_int(value) and value > 0 else 0


def _border_lengths(prefix_text: str, suffix_text: str) -> list[int]:
    """Return every length where a suffix of *suffix* equals a prefix of *prefix*.

    Uses the prefix-function (KMP failure function) of
    ``prefix_text + sentinel + suffix_text``: every border of that
    concatenation is exactly a length L such that the last L characters
    of *suffix_text* equal the first L characters of *prefix_text*, and
    the sentinel guarantees L never exceeds either text.  The returned
    lengths are strictly descending, so the first fitting the overlap
    budget is the longest such match.
    """
    text = prefix_text + _BORDER_SENTINEL + suffix_text
    failure = [0] * len(text)
    for i in range(1, len(text)):
        length = failure[i - 1]
        while length > 0 and text[i] != text[length]:
            length = failure[length - 1]
        if text[i] == text[length]:
            length += 1
        failure[i] = length
    borders: list[int] = []
    length = failure[-1] if text else 0
    while length > 0:
        borders.append(length)
        length = failure[length - 1]
    return borders


def _join_spaced(left: str, right: str) -> str:
    """Concatenate two texts, inserting one space only when needed."""
    if not left:
        return right
    if not right:
        return left
    if left[-1].isspace() or right[0].isspace():
        return left + right
    return left + " " + right


def _merge_pair(left: str, right: str, budget: int) -> str:
    """Merge two adjacent chunk texts losslessly.

    Removes the longest exact suffix/prefix match whose whitespace word
    count fits *budget*; the word count never exceeds the splitter's
    token count for the same text, so a genuine overlap always fits.
    With no fitting match the texts are concatenated without deletion —
    never trimmed by character count and never fuzzy-matched.
    """
    if budget <= 0 or not left or not right:
        return _join_spaced(left, right)
    for length in _border_lengths(right, left):
        if len(left[-length:].split()) <= budget:
            return left + right[length:]
    return _join_spaced(left, right)


def _mark_retrieved(row: Mapping[str, Any]) -> dict[str, Any]:
    """Copy one ranked row and attach the assembly markers."""
    prepared = dict(row)
    prepared["_assembly_merged"] = False
    prepared["_assembly_chunk_count"] = 1
    prepared["_assembly_expanded"] = False
    return prepared


def _mark_expanded(row: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one lineage neighbour row into an assembly candidate.

    The row gains the public result fields it did not need as a bare
    neighbour, and deliberately carries **no** retrieval score: expanded
    evidence was never ranked, so giving it one would misrepresent it.
    """
    metadata = dict(row.get("metadata") or {})
    prepared = dict(row)
    fallback_source = metadata.get("file_path") or metadata.get("file_name") or "unknown"
    prepared.setdefault("source", fallback_source)
    prepared.setdefault("page_label", metadata.get("page_label"))
    prepared["reranked"] = False
    prepared.pop("score", None)
    prepared.pop("score_kind", None)
    prepared["_assembly_merged"] = False
    prepared["_assembly_chunk_count"] = 1
    prepared["_assembly_expanded"] = True
    return prepared


def _best_scored(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Return the highest-scoring constituent that carries a score.

    Ties resolve to the lowest ``source_chunk_index`` so the choice is
    deterministic.  A unit of expansion-only rows has no scored
    constituent and gets ``None``.
    """
    best: Mapping[str, Any] | None = None
    for row in rows:
        if "score" not in row:
            continue
        if best is None or row["score"] > best["score"]:
            best = row
    return best


def _merge_unit(rows: Sequence[Mapping[str, Any]], budget: int) -> dict[str, Any]:
    """Merge one contiguous run of rows into a single result row.

    The lowest-index constituent supplies identity (``id``, ``metadata``,
    ``chunk_id``, ``source_chunk_index``); the best-scoring constituent
    supplies ``score``, ``score_kind`` and ``reranked`` — the merged row
    answers "how relevant is this passage", and the best-matching part is
    what made it relevant (design D3).
    """
    base = dict(rows[0])
    text = rows[0].get("text") or ""
    for row in rows[1:]:
        text = _merge_pair(text, row.get("text") or "", budget)
    merged = dict(base)
    merged["text"] = text
    best = _best_scored(rows)
    if best is not None:
        merged["score"] = best["score"]
        merged["score_kind"] = best.get("score_kind")
        merged["reranked"] = bool(best.get("reranked"))
    else:
        merged.pop("score", None)
        merged.pop("score_kind", None)
        merged["reranked"] = False
    chunk_ids = [_field(row, "chunk_id") for row in rows]
    chunk_ids = [chunk_id for chunk_id in chunk_ids if chunk_id is not None]
    if chunk_ids:
        merged[MERGED_CHUNK_IDS_KEY] = chunk_ids
    merged["_assembly_merged"] = len(rows) > 1
    merged["_assembly_chunk_count"] = len(rows)
    merged["_assembly_expanded"] = all(bool(row.get("_assembly_expanded")) for row in rows)
    return merged


def _ordered_units(candidates: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Partition candidates into contiguous runs, in emission order.

    Candidates sharing ``(source_id, source_version)`` with consecutive
    ``source_chunk_index`` values form one unit; anything else — other
    sources, other versions, index gaps, or rows without lineage — stands
    alone.  A repeated index keeps its first (highest-ranked) candidate
    because the rows rank in descending score order and the stored chunk
    is the same.  Units are returned at the position of their
    earliest-ranked constituent so ranked order survives assembly.
    """
    buckets: dict[tuple[str, str], dict[int, int]] = {}
    alias: dict[int, int] = {}
    for position, row in enumerate(candidates):
        key = _lineage_unit_key(row)
        if key is None:
            continue
        seen = buckets.setdefault((key[0], key[1]), {})
        if key[2] in seen:
            # A repeated index is the same stored chunk surfacing twice;
            # it resolves to its first (highest-ranked) candidate's unit.
            alias[position] = seen[key[2]]
        else:
            seen[key[2]] = position
    position_units: dict[int, int] = {}
    units: list[list[dict[str, Any]]] = []
    for by_index in buckets.values():
        indices = sorted(by_index)
        start = 0
        for offset in range(1, len(indices) + 1):
            if offset < len(indices) and indices[offset] == indices[offset - 1] + 1:
                continue
            group = indices[start:offset]
            unit_id = len(units)
            units.append([candidates[by_index[index]] for index in group])
            for index in group:
                position_units[by_index[index]] = unit_id
            start = offset
    ordered: list[list[dict[str, Any]]] = []
    emitted: set[int] = set()
    for position in range(len(candidates)):
        unit_id = position_units.get(alias.get(position, position))
        if unit_id is None:
            ordered.append([candidates[position]])
        elif unit_id not in emitted:
            emitted.add(unit_id)
            ordered.append(units[unit_id])
    return ordered


def assemble(
    rows: Sequence[Mapping[str, Any]],
    *,
    chunk_overlap: int,
    expand_window: int,
    store: VectorStore,
    collection: str,
) -> list[dict[str, Any]]:
    """Assemble ranked retrieval rows into the returned context.

    Runs the two assembly operations in order — bounded neighbour
    expansion, then contiguity-driven merging — and never re-ranks,
    re-scores or drops evidence.  The relative order established by
    ranking is preserved: a merged row takes the position of its
    earliest-ranked constituent, and rows added purely by expansion
    follow the ranked rows.

    Args:
        rows: The ranked, truncated result rows from retrieval.
        chunk_overlap: The configured ``chunking.chunk_overlap`` token
            budget bounding how large an exact boundary match may be.
        expand_window: Neighbours requested per side of each retrieved
            chunk; zero or less disables expansion.
        store: The vector store neighbours are read through.
        collection: The collection the rows were retrieved from.

    Returns:
        Assembled rows carrying the assembly-internal marker fields
        (see :data:`ASSEMBLY_INTERNAL_FIELDS`), merged rows additionally
        carrying :data:`MERGED_CHUNK_IDS_KEY`.
    """
    if not rows:
        return []
    candidates = [_mark_retrieved(row) for row in rows]
    window = _positive_int(expand_window)
    if window:
        # Expansion composes with merging by design: neighbours join the
        # candidate set and merge under the same contiguity rules.
        candidates.extend(
            _mark_expanded(row) for row in neighbours(rows, store, collection, window)
        )
    budget = _positive_int(chunk_overlap)
    assembled: list[dict[str, Any]] = []
    for unit in _ordered_units(candidates):
        if len(unit) == 1:
            assembled.append(unit[0])
        else:
            assembled.append(_merge_unit(unit, budget))
    return assembled


def promote_assembly_diagnostics(rows: list[dict[str, Any]]) -> None:
    """Rename the internal assembly markers to their diagnostics names.

    Called by ``search()`` only when diagnostics are enabled, so each row
    reports whether it was merged, from how many chunks, and whether it
    was added by expansion.  Without diagnostics the internal names are
    stripped instead and the public result shape stays stable.
    """
    for row in rows:
        row["assembly_merged"] = row.pop("_assembly_merged", False)
        row["assembly_chunk_count"] = row.pop("_assembly_chunk_count", 1)
        row["assembly_expanded"] = row.pop("_assembly_expanded", False)
