"""Deterministic citation construction for grounded answering.

Citations are built by the system from the lineage of the chunks it
supplied as context — the model's output is used only to learn *which*
supplied ordinals it leaned on, never as the origin of an identifier
(design D5):

* Bracket groups of comma-separated integers are parsed from the answer
  text; whitespace inside the brackets is tolerated (``[ 3 ]``).
* A group containing anything non-numeric is dropped whole (``[1, x]``
  cites nothing).  Digit-ness is checked with ``str.isdecimal`` so
  characters that pass ``isdigit`` but crash ``int()`` (superscripts
  such as ``²``) are dropped, not raised.
* An ordinal string longer than 9 digits is rejected with an
  actionable ``ValueError`` before conversion: it cannot index the
  supplied evidence, and CPython's integer parser raises an opaque
  conversion-limit error on multi-thousand-digit strings.
* Ordinals outside the supplied range (``< 1`` or ``> len(evidence)``)
  are discarded rather than resolved.
* Duplicates are deduplicated and the result sorted ascending.
* A citation entry carries every constituent ``chunk_id`` of a merged
  row, not only the merged row's representative.
"""

from __future__ import annotations

import re

# Bracket groups whose content is digits and commas/whitespace only.
_BRACKET_GROUP = re.compile(r"\[([0-9,\s]+)\]")

#: Ordinals index the supplied evidence list, so anything longer than
#: nine digits is absurd input, not a citation.  The bound also keeps
#: ``int()`` clear of CPython's integer-string conversion limit.
_MAX_ORDINAL_DIGITS = 9


def parse_citation_ordinals(answer_text: str, max_ordinal: int) -> list[int]:
    """Extract valid supplied-source ordinals from answer text.

    Args:
        answer_text: The synthesised answer text.
        max_ordinal: Highest valid ordinal (the number of supplied
            sources).

    Returns:
        Sorted unique ordinals in ``[1, max_ordinal]``.

    Raises:
        ValueError: When a bracket group contains an ordinal string
            longer than :data:`_MAX_ORDINAL_DIGITS` digits — absurd
            input that is rejected before integer conversion rather
            than reaching ``int()``'s conversion limit.
    """
    valid: set[int] = set()
    for group in _BRACKET_GROUP.findall(answer_text or ""):
        parts = [part.strip() for part in group.split(",")]
        # Any empty or non-numeric part (e.g. from a trailing comma)
        # drops the whole group together.
        numbers: list[int] = []
        for part in parts:
            if not part.isdecimal():
                numbers = []
                break
            if len(part) > _MAX_ORDINAL_DIGITS:
                raise ValueError(
                    f"Citation ordinal has more than {_MAX_ORDINAL_DIGITS} digits "
                    f"(got {len(part)}); supplied sources are numbered from 1, so "
                    "this cannot be a valid citation."
                )
            numbers.append(int(part))
        if not numbers:
            continue
        for number in numbers:
            if 1 <= number <= max_ordinal:
                valid.add(number)
    return sorted(valid)


def build_citations(evidence: list[dict], ordinals: list[int]) -> list[dict]:
    """Build the citation list from supplied evidence rows.

    Args:
        evidence: The evidence rows supplied as context (each carrying
            ``chunk_id``, ``chunk_ids`` and lineage fields).
        ordinals: Valid parsed ordinals, ascending.

    Returns:
        One citation entry per ordinal, carrying that evidence row's
        full lineage including every constituent ``chunk_id`` of a
        merged row.
    """
    citations: list[dict] = []
    for ordinal in ordinals:
        row = evidence[ordinal - 1]
        chunk_ids = list(row.get("chunk_ids") or [])
        if row.get("chunk_id") is not None and row["chunk_id"] not in chunk_ids:
            chunk_ids.insert(0, row["chunk_id"])
        citations.append(
            {
                "ordinal": ordinal,
                "chunk_id": row.get("chunk_id"),
                "chunk_ids": chunk_ids,
                "source_id": row.get("source_id"),
                "source_version": row.get("source_version"),
                "source": row.get("source"),
                "source_chunk_index": row.get("source_chunk_index"),
                "score": row.get("score"),
                "score_kind": row.get("score_kind"),
            }
        )
    return citations
