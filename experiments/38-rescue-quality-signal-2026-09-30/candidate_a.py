"""Candidate A: frozen-token word frequency and Unicode script consistency."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any

import regex
from wordfreq import zipf_frequency

LANGUAGES = ("en", "es", "fr", "de", "it", "pt", "nl", "ar", "hi", "bn")

# Enumerate the installed Unicode script table instead of guessing from character
# names. This internal enumeration is version-bound in the scoring checkpoint;
# matching itself uses regex's documented Script property syntax.
_aliases = regex._regex.get_properties()["SCRIPT"][1]
_names: dict[int, str] = {}
for _name, _code in _aliases.items():
    _names.setdefault(_code, _name)
_SCRIPT_PATTERNS = [
    (name, regex.compile(rf"\p{{Script={name}}}"))
    for name in _names.values()
    if name not in {"COMMON", "INHERITED"}
]
_LETTER = regex.compile(r"\p{L}")


@lru_cache(maxsize=100_000)
def _real_word(token: str) -> bool:
    return any(zipf_frequency(token, language) >= 1.0 for language in LANGUAGES)


def real_word_ratio(tokens: list[str]) -> float:
    """Return the share of frozen tokens with Zipf frequency at least 1.0."""
    return sum(_real_word(token) for token in tokens) / len(tokens) if tokens else 0.0


@lru_cache(maxsize=10_000)
def _script(letter: str) -> str | None:
    return next((name for name, pattern in _SCRIPT_PATTERNS if pattern.fullmatch(letter)), None)


def script_consistency(text: str) -> tuple[float, dict[str, int]]:
    """Count letters by Unicode script, excluding Common and Inherited."""
    counts = Counter(script for letter in _LETTER.findall(text) if (script := _script(letter)))
    total = sum(counts.values())
    return (max(counts.values()) / total if total else 0.0), dict(counts)


def score_a(text: str, rule: Any) -> dict:
    """Calculate design D3 exactly, using the supplied frozen token rule."""
    a1 = real_word_ratio(rule.tokens(text))
    a2, scripts = script_consistency(text)
    return {"A1": a1, "A2": a2, "score": min(a1, a2), "script_letter_counts": scripts}
