"""Deterministic Chroma collection naming for immutable experiment indexes.

Chroma collection names must be 3–512 characters long, start and end
with an alphanumeric character, and contain only letters, digits,
``.``, ``_``, and ``-`` in between.  Experiment index names are derived
from the immutable index identity (experiment, corpus/config, embedding
provider/model, parser, chunking) so the same inputs always resolve to
the same collection.  Cell IDs and repetitions that only change
retrieval settings are deliberately NOT part of the name — they reuse
the index read-only and live in checkpoint/result metadata.
"""

from __future__ import annotations

import hashlib
import re

_MIN_NAME_LENGTH = 3
_MAX_NAME_LENGTH = 512
_HASH_SUFFIX_LENGTH = 8

# Start/end alphanumeric; middle allows alphanumerics plus . _ -
_COLLECTION_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]$")


def sanitize_collection_component(value: str) -> str:
    """Normalise one name component to a lowercase alphanumeric slug.

    Runs of non-alphanumeric characters collapse to a single ``-`` and
    leading/trailing separators are stripped, so model identifiers like
    ``Qwen3 8B`` or ``openai/gpt-oss-20b`` become safe name parts.

    Args:
        value: Raw component text (experiment ID, corpus, model, ...).

    Returns:
        The sanitised lowercase component; empty when nothing remains.
    """
    parts = re.split(r"[^A-Za-z0-9]+", value.strip())
    return "-".join(part.lower() for part in parts if part)


def validate_collection_name(name: str) -> None:
    """Assert a collection name satisfies Chroma's naming rules.

    Args:
        name: Candidate collection name.

    Raises:
        ValueError: When the length or character rules are violated.
    """
    if not _COLLECTION_NAME_RE.match(name):
        raise ValueError(
            f"Invalid Chroma collection name {name!r}: must be 3-512 characters, "
            "start and end with a letter or digit, and contain only letters, "
            "digits, '.', '_', and '-'."
        )


def _fit_to_rules(slug: str) -> str:
    """Force a joined slug inside the 3-512 alphanumeric-boundary window.

    Overlong slugs truncate deterministically and gain a sha256 suffix so
    two distinct long identities never collide on the same short prefix.
    Slugs shorter than three characters gain the same suffix.

    Args:
        slug: Joined, sanitised slug (may violate length rules).

    Returns:
        A slug satisfying every Chroma naming rule.
    """

    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HASH_SUFFIX_LENGTH]

    if len(slug) > _MAX_NAME_LENGTH:
        keep = _MAX_NAME_LENGTH - _HASH_SUFFIX_LENGTH - 1
        slug = f"{slug[:keep].rstrip('._-')}-{_digest(slug)}"
    if len(slug) < _MIN_NAME_LENGTH:
        slug = f"{slug}-{_digest(slug)}" if slug else _digest(slug)
    # Truncation/padding can leave separator edges; strip them, then
    # re-check the length because stripping may shorten below three.
    slug = slug.strip("._-")
    if len(slug) < _MIN_NAME_LENGTH:
        slug = f"{slug}-{_digest(slug)}" if slug else _digest(slug)
    return slug


def experiment_collection_name(
    *,
    experiment_id: str,
    corpus: str,
    provider: str,
    model: str,
    parser: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> str:
    """Derive the deterministic collection name for one immutable index.

    The name encodes everything that changes indexed content: the
    experiment, the corpus/config identity, the embedding provider and
    model, the parser (when parsed text differs), and the chunking
    configuration.  Example:
    ``exp14-qasper-openrouter-qwen3-8b-liteparse-cs512-co100``.

    Args:
        experiment_id: Experiment identifier, e.g. ``exp14``.
        corpus: Corpus/config identity, e.g. ``qasper`` or ``freshstack-v2``.
        provider: Effective embedding backend (``llamacpp``, ``openrouter``...).
        model: Embedding model identifier.
        parser: Document parser used at ingest time, when it changes the
            indexed text (e.g. ``liteparse`` vs ``pypdf``).
        chunk_size: Chunk size used to build the index.
        chunk_overlap: Chunk overlap used to build the index.

    Returns:
        A collection name satisfying every Chroma naming rule.

    Raises:
        ValueError: Never for sanitised input; the returned name is
            validated before returning so rule regressions fail loudly.
    """
    components = [experiment_id, corpus, provider, model]
    if parser:
        components.append(parser)
    if chunk_size is not None:
        components.append(f"cs{chunk_size}")
    if chunk_overlap is not None:
        components.append(f"co{chunk_overlap}")
    slug = "-".join(sanitize_collection_component(component) for component in components)
    slug = _fit_to_rules(slug)
    validate_collection_name(slug)
    return slug
