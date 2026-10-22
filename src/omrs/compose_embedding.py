"""Embedding provider listing and "Check model" (ADR-081, design D8).

Composition-root surface for the embedding routes. The web transport may not
call ``get_settings()``, so these functions read the settings here.

* :func:`provider_listing` lists the registered embedding providers and
  whether each one can be built in this install.
* :func:`server_default_identity` names the provider and the model that the
  ``EMBED_*`` settings select.
* :func:`check_embedding_model` embeds one probe text with a throwaway embedder
  and reports the vector size and length. It never raises for a failed probe:
  a failed check is a result with a plain-English reason. Credentials are
  removed from every reason.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath
from typing import Any

from .config import Settings, get_settings
from .core.norm_guard import ENABLE_SETTING, TOLERANCE_SETTING, is_within_tolerance, l2_norm
from .core.providers.embeddings import registry as embed_registry
from .core.settings import provider_secret_values
from .core.vectordb.identity import (
    EmbeddingIdentity,
    RedactionSecrets,
    embedding_identity_from_settings,
)

logger = logging.getLogger(__name__)

#: The text the check embeds.
PROBE_TEXT = "OMRS model check"
#: Seconds the llama.cpp model-list request may take.
LIST_TIMEOUT_SECONDS = 5.0

ModelLister = Callable[[str], list[str]]


class UnknownEmbeddingProviderError(KeyError):
    """The provider name is not in the embedding registry."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "unknown embedding provider"


def server_default_identity(settings: Settings | None = None) -> EmbeddingIdentity:
    """Return the provider and model that the ``EMBED_*`` settings select."""
    return embedding_identity_from_settings(settings or get_settings())


def _first_line(text: str) -> str:
    """Collapse a multi-line message to one line."""
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _build_error(exc: Exception) -> str:
    """Return the reason for an embedder that cannot be built."""
    return _first_line(str(exc)) or type(exc).__name__


def provider_listing(names: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Return ``{name, available, reason}`` for each registered embedding provider.

    A provider is unavailable when its optional dependency is missing. The
    reason then names the extra to install.

    Args:
        names: Provider names to list. ``None`` lists every registered provider.
    """
    items: list[dict[str, Any]] = []
    for name in names if names is not None else embed_registry.available():
        try:
            embed_registry.get(name)
        except ImportError as exc:
            items.append({"name": name, "available": False, "reason": _build_error(exc)})
        else:
            items.append({"name": name, "available": True, "reason": None})
    return items


def _served_models(url: str) -> list[str]:
    """Return the model names that a llama.cpp server lists at ``{url}/models``."""
    import httpx

    response = httpx.get(f"{url.rstrip('/')}/models", timeout=LIST_TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    names: list[str] = []
    for entry in body.get("data") or []:
        if entry.get("id"):
            names.append(str(entry["id"]))
    for entry in body.get("models") or []:
        for key in ("model", "name"):
            if entry.get(key):
                names.append(str(entry[key]))
    return list(dict.fromkeys(names))


def _is_served(model: str, served: Sequence[str]) -> bool:
    """Return whether a served name equals the model name or its file name."""
    file_name = PurePosixPath(model).name
    return any(name == model or PurePosixPath(name).name == file_name for name in served)


def _result(
    ok: bool, dimensions: int | None, norm: float | None, reason: str | None
) -> dict[str, Any]:
    return {"ok": ok, "dimensions": dimensions, "norm": norm, "reason": reason}


def _failure(reason: str, redact: Callable[[str], str]) -> dict[str, Any]:
    return _result(False, None, None, redact(reason))


def _llamacpp_refusal(
    settings: Settings, model: str, lister: ModelLister, redact: Callable[[str], str]
) -> dict[str, Any] | None:
    """Return a failed result when the llama.cpp server does not list the model."""
    url = settings.llamacpp_embed_url
    try:
        served = lister(url)
    except Exception as exc:
        text = _first_line(str(exc)) or type(exc).__name__
        return _failure(f"The llama.cpp server at {url} did not list its models: {text}", redact)
    if _is_served(model, served):
        return None
    names = ", ".join(served) if served else "none"
    return _failure(
        f"The llama.cpp server does not serve {model}. It serves: {names}. "
        f"llama.cpp ignores the model name in a request, so the name must match a served model.",
        redact,
    )


def check_embedding_model(
    provider: str,
    model: str,
    *,
    settings: Settings | None = None,
    redact: Callable[[str], str] | None = None,
    list_models: ModelLister | None = None,
) -> dict[str, Any]:
    """Embed one probe text with ``provider`` and ``model`` and report the vector.

    The embedder is a throwaway: it is not added to any Engine.

    Args:
        provider: A registered embedding provider.
        model: The model name.
        settings: Resolved settings. ``None`` reads them.
        redact: Removes credentials from reasons. ``None`` removes the
            configured OpenRouter and Chroma Cloud values.
        list_models: Returns the names a llama.cpp server serves; takes the
            server URL. ``None`` asks the server.

    Returns:
        ``{ok, dimensions, norm, reason}``. ``reason`` is ``None`` when the
        check passes, else a plain-English line.

    Raises:
        UnknownEmbeddingProviderError: If ``provider`` is not registered.
    """
    settings = settings or get_settings()
    redactor = (
        redact
        or RedactionSecrets(
            chroma_cloud_api_key=settings.chroma_cloud_api_key,
            chroma_cloud_tenant=settings.chroma_cloud_tenant,
            chroma_cloud_database=settings.chroma_cloud_database,
            provider_keys=provider_secret_values(settings),
        ).redact
    )
    model = model.strip()
    try:
        build = embed_registry.get(provider)
    except KeyError as exc:
        raise UnknownEmbeddingProviderError(str(exc.args[0] if exc.args else provider)) from exc
    except ImportError as exc:
        return _failure(_build_error(exc), redactor)
    if not model:
        return _failure("Enter a model name.", redactor)
    if provider == "llamacpp":
        refusal = _llamacpp_refusal(settings, model, list_models or _served_models, redactor)
        if refusal is not None:
            return refusal
    try:
        vector = list(build(settings, model=model).get_text_embedding(PROBE_TEXT))
    except Exception as exc:
        text = _first_line(str(exc)) or type(exc).__name__
        logger.info("Model check failed for %s/%s: %s", provider, model, type(exc).__name__)
        return _failure(f"{provider} could not embed with {model}: {text}", redactor)
    if not vector:
        return _failure(f"{provider} returned no vector for {model}.", redactor)
    norm = l2_norm(vector)
    guard = settings.embedding
    if guard.norm_guard_enabled and not is_within_tolerance(norm, guard.norm_tolerance):
        reason = (
            f"{model} returns vectors of length {norm:.4f} and not 1.0, so ingestion would "
            f"refuse these vectors. Use a model that returns unit-length vectors, or change "
            f"{TOLERANCE_SETTING} or {ENABLE_SETTING} on the server."
        )
        return _result(False, len(vector), norm, redactor(reason))
    return _result(True, len(vector), norm, None)
