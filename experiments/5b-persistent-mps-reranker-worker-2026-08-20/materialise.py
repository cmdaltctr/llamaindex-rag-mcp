"""Deterministic text materialisation for the 5b longevity schedule.

The committed ``longevity_schedule.json`` records only shapes and seeds; its
``materialisation_rule`` states: "harness synthesises query and candidate
text from a fixed 512-word vocabulary using
random.Random(text_materialisation_seed); word counts equal the stratum
approximate token length (1 word ~= 1 token)".

The fixed vocabulary is generated once from syllable templates seeded with
the schedule seed (20260821), giving 512 unique natural-shaped words whose
token lengths behave like real words.  Queries draw ``QUERY_WORDS`` words;
each candidate draws exactly the stratum's approximate token length in
words.  Identical schedule rows therefore materialise identical text, and
different seeds differ.
"""

from __future__ import annotations

import random
from typing import Any

VOCAB_SIZE = 512
QUERY_WORDS = 8
_SCHEDULE_SEED = 20260821
_ONSETS = (
    "b",
    "c",
    "d",
    "f",
    "g",
    "h",
    "j",
    "k",
    "l",
    "m",
    "n",
    "p",
    "r",
    "s",
    "t",
    "v",
    "w",
    "z",
    "br",
    "cl",
    "gr",
    "pl",
    "st",
    "tr",
    "sh",
    "th",
    "sp",
    "dr",
    "fl",
    "cr",
)
_NUCLEI = ("a", "e", "i", "o", "u", "ai", "ee", "ie", "oa", "oo")
_CODAS = ("", "", "n", "t", "s", "r", "l", "m", "d", "k", "x", "p")


def build_vocabulary() -> tuple[str, ...]:
    """Return the fixed 512-word vocabulary (deterministic, unique)."""
    rng = random.Random(_SCHEDULE_SEED)  # noqa: S311 — seeded determinism is contractual
    words: list[str] = []
    seen: set[str] = set()
    while len(words) < VOCAB_SIZE:
        syllables = rng.choice((1, 2, 2, 3))
        word = "".join(
            rng.choice(_ONSETS) + rng.choice(_NUCLEI) + rng.choice(_CODAS) for _ in range(syllables)
        )
        if word and word not in seen:
            seen.add(word)
            words.append(word)
    return tuple(words)


_VOCABULARY = build_vocabulary()


def materialise_request(row: dict[str, Any]) -> dict[str, Any]:
    """Materialise one schedule row into query text and candidate texts.

    Args:
        row: A ``longevity_schedule.json`` request with
            ``stratum_candidate_count``, ``stratum_approx_tokens_per_candidate``,
            ``request_index`` and ``text_materialisation_seed``.

    Returns:
        ``{"query": str, "candidates": [{"doc_id", "text"}, ...]}`` where
        ``doc_id`` is ``r<request_index>_c<candidate>``.
    """
    rng = random.Random(int(row["text_materialisation_seed"]))  # noqa: S311 — schedule-fixed seed
    vocabulary = _VOCABULARY
    query = " ".join(rng.choice(vocabulary) for _ in range(QUERY_WORDS))
    target_words = int(row["stratum_approx_tokens_per_candidate"])
    count = int(row["stratum_candidate_count"])
    index = int(row["request_index"])
    candidates = [
        {
            "doc_id": f"r{index}_c{i}",
            "text": " ".join(rng.choice(vocabulary) for _ in range(target_words)),
        }
        for i in range(count)
    ]
    return {"query": query, "candidates": candidates}
