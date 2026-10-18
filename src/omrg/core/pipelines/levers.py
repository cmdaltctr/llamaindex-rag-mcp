"""Setting levers a graph may override, and settings the host owns.

A lever path names one field of :class:`~omrg.core.settings.EffectiveSettings`
as ``block.field``. Graphs may override only the documented operation
controls and index-shaping settings below. Provider and model identity,
secrets, storage locations and reader backends stay with the host: a graph
cannot change ``.env``, construct a different provider or download a model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from ..settings import EffectiveSettings


@dataclass(frozen=True)
class LeverSpec:
    """One overridable setting.

    Attributes:
        path: ``block.field`` path into ``EffectiveSettings``.
        adapter: Strict validator for override values.
        index_shaping: Whether the lever changes stored chunks or vectors.
        description: Short help text.
    """

    path: str
    adapter: TypeAdapter[Any]
    index_shaping: bool
    description: str

    @property
    def env_name(self) -> str:
        """Return the nested environment variable for the lever."""
        return self.path.upper().replace(".", "__")

    def validate(self, value: Any) -> Any:
        """Validate ``value`` strictly and return it."""
        return self.adapter.validate_python(value, strict=True)


def _lever(path: str, annotation: Any, description: str, *, shaping: bool = False) -> LeverSpec:
    return LeverSpec(path, TypeAdapter(annotation), shaping, description)


_POSITIVE_INT = Annotated[int, Field(ge=1)]
_UNIT_FLOAT = Annotated[float, Field(ge=0.0, le=1.0)]

ALLOWED_LEVERS: Mapping[str, LeverSpec] = {
    spec.path: spec
    for spec in (
        _lever("retrieval.top_k", _POSITIVE_INT, "Results returned after selection."),
        _lever("retrieval.rerank_enabled", bool, "Run the cross-encoder reranker."),
        _lever("retrieval.hybrid_enabled", bool, "Combine dense and sparse retrieval."),
        _lever("retrieval.hybrid_rrf_k", _POSITIVE_INT, "RRF rank constant."),
        _lever("retrieval.similarity_threshold", _UNIT_FLOAT, "Dense similarity floor."),
        _lever("retrieval.rerank_fetch_multiplier", _POSITIVE_INT, "Rerank candidate factor."),
        _lever("answer.verify_claims", bool, "Run opt-in claim verification."),
        _lever("chunking.chunk_size", _POSITIVE_INT, "Sentence chunk size.", shaping=True),
        _lever(
            "chunking.chunk_overlap", Annotated[int, Field(ge=0)], "Chunk overlap.", shaping=True
        ),
        _lever("chunking.markdown_chunk_size", _POSITIVE_INT, "Markdown chunk size.", shaping=True),
        _lever("chunking.code_chunk_lines", _POSITIVE_INT, "Code chunk lines.", shaping=True),
        _lever(
            "chunking.strategy_fallback",
            Literal["markdown", "code", "sentence"],
            "Fallback chunking strategy.",
            shaping=True,
        ),
        _lever(
            "metadata.taxonomy_mode",
            Literal["category", "file_type"],
            "Metadata taxonomy mode.",
            shaping=True,
        ),
    )
}

# Host-owned settings: matched by exact path, block prefix or name fragment.
_HOST_OWNED_EXACT = frozenset(
    {
        "embed_provider",
        "embed_model",
        "metadata_llm_provider",
        "local_backend",
        "cloud_backend",
        "vector_store",
        "lancedb_uri",
        "chroma_persist_dir",
        "collection_name",
        "pdf_reader",
        "rag_profile",
        "profile_name",
        "retrieval.rerank_model",
        "retrieval.rerank_backend",
        "retrieval.hybrid_sparse_backend",
        "answer.verify_model",
        "answer.verify_provider",
    }
)
_HOST_OWNED_HINTS = {
    "pdf_reader": (
        " To read PDF files differently in one pipeline, set the reader on the "
        "Read document step instead."
    ),
    "embed_model": " Set the model on the profile's Embed step.",
    "embed_provider": " Set the model on the profile's Embed step.",
}
_HOST_OWNED_PREFIXES = ("embedding.", "ingestion.")
_HOST_OWNED_FRAGMENTS = ("api_key", "_url", "secret", "token", "password", "_model", "_uri")


def is_host_owned(path: str) -> bool:
    """Return whether ``path`` names a setting only the host may change."""
    if path in _HOST_OWNED_EXACT or path.startswith(_HOST_OWNED_PREFIXES):
        return True
    return any(fragment in path for fragment in _HOST_OWNED_FRAGMENTS)


def lever_error(path: str, value: Any) -> tuple[str, str] | None:
    """Check one override and describe the problem.

    Args:
        path: Lever path such as ``retrieval.top_k``.
        value: Proposed value.

    Returns:
        ``None`` when valid, else ``(kind, message)`` where ``kind`` is
        ``"host_owned"`` or ``"invalid"``.
    """
    spec = ALLOWED_LEVERS.get(path)
    if spec is None:
        if is_host_owned(path):
            hint = _HOST_OWNED_HINTS.get(path, "")
            return (
                "host_owned",
                f"'{path}' is owned by the host configuration. Change it in the "
                f"environment and restart OMRG; a graph cannot change it.{hint}",
            )
        allowed = ", ".join(sorted(ALLOWED_LEVERS))
        return ("invalid", f"'{path}' is not an allowed graph lever. Allowed levers: {allowed}.")
    try:
        spec.validate(value)
    except ValidationError as exc:
        detail = exc.errors()[0].get("msg", "invalid value")
        return ("invalid", f"'{path}' rejects {value!r}: {detail}.")
    return None


def read_lever(settings: EffectiveSettings, path: str) -> Any:
    """Return the current value of ``path`` from ``settings``."""
    block_name, field_name = path.split(".", 1)
    return getattr(getattr(settings, block_name), field_name)


def apply_levers(settings: EffectiveSettings, values: Mapping[str, Any]) -> EffectiveSettings:
    """Return a copy of ``settings`` with validated lever values applied.

    Args:
        settings: Frozen base settings.
        values: Lever path to value. Every path must be in
            :data:`ALLOWED_LEVERS`; values are validated again here.

    Returns:
        A new frozen settings object. ``settings`` is unchanged.

    Raises:
        KeyError: If a path is not an allowed lever.
        pydantic.ValidationError: If a value fails its lever validator.
    """
    by_block: dict[str, dict[str, Any]] = {}
    for path, value in values.items():
        spec = ALLOWED_LEVERS[path]
        block_name, field_name = path.split(".", 1)
        by_block.setdefault(block_name, {})[field_name] = spec.validate(value)
    update = {
        block_name: getattr(settings, block_name).model_copy(update=fields)
        for block_name, fields in by_block.items()
    }
    return settings.model_copy(update=update) if update else settings
