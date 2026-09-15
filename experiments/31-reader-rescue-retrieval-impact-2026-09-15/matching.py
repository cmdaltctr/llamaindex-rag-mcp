"""Frozen text-span matching rule for Experiment 31 (task 1.4).

One rule decides BOTH evidence recoverability (span vs a cell's full
extraction) and retrieval hits (span vs a retrieved chunk) in every cell.
The rule is frozen before measured execution; ``cells.json`` records its
terms and ``freeze.py`` pins this file's hash.

Rule (see protocol.md "Text-Span Matching Rule"):
1. Normalise span and target identically: NFKC, casefold, typographic
   character folding, end-of-line hyphen rejoin, whitespace collapse.
2. Exact stage: normalised span is a substring of normalised target.
3. Fuzzy stage (spans of >= 8 word tokens): hit when >= 0.85 of the
   span's word 8-grams appear in the target's 8-gram set.

Deterministic, dependency-free, and order-preserving within each 8-gram
so page headers interleaved by different extractors cannot break a match
that is locally intact.
"""

from __future__ import annotations

import re
import unicodedata

NGRAM_N = 8
FUZZY_THRESHOLD = 0.85

TYPOGRAPHIC_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201f": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }
)

_HYPHEN_SPLIT = re.compile(r"(\w)-\s+(\w)")
_HYPHEN_INNER = re.compile(r"(\w)-(\w)")
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+", re.UNICODE)


def normalise(text: str) -> str:
    """Apply the frozen normalisation pipeline to *text*."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = folded.translate(TYPOGRAPHIC_MAP)
    # Rejoin words the extractor split across a line break, then fold the
    # remaining intra-word hyphens. Both transforms run on span and target
    # identically, so a compound written "well-known" in one extraction and
    # "well-\\nknown" in another normalises to the same form.
    rejoined = _HYPHEN_SPLIT.sub(r"\1\2", folded)
    rejoined = _HYPHEN_INNER.sub(r"\1\2", rejoined)
    return _WS.sub(" ", rejoined).strip()


def word_tokens(text: str) -> list[str]:
    """Return the case-normalised word tokens of *text*."""
    return _TOKEN.findall(normalise(text))


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def span_hit(span: str, target: str) -> bool:
    """Decide whether *target* contains *span* under the frozen rule.

    Args:
        span: Gold evidence span text.
        target: Candidate text (full extraction or one retrieved chunk).

    Returns:
        True when the exact stage or the fuzzy stage accepts the match.
    """
    if not span.strip() or not target.strip():
        return False
    norm_span = normalise(span)
    norm_target = normalise(target)
    if not norm_span or not norm_target:
        return False
    if norm_span in norm_target:
        return True
    span_tokens = _TOKEN.findall(norm_span)
    if len(span_tokens) < NGRAM_N:
        return False  # short spans: exact stage only (frozen)
    target_tokens = _TOKEN.findall(norm_target)
    if len(target_tokens) < NGRAM_N:
        return False
    span_grams = _ngrams(span_tokens, NGRAM_N)
    target_grams = _ngrams(target_tokens, NGRAM_N)
    overlap = len(span_grams & target_grams)
    return overlap / len(span_grams) >= FUZZY_THRESHOLD
