"""Provider connection summary and test targets (design D13).

Pure functions over a resolved ``Settings``. ``compose.connection_summary``
and ``compose.connection_targets`` are the thin entries that read the
settings; this module lives beside ``compose.py`` because that file sits
at the 500-line ceiling.

The summary lists the three LLM registry providers (``ollama``,
``llamacpp``, ``openrouter``) with their endpoint URLs, configured model
names, whether a key is set, and the roles that use them. Roles follow the
startup rules (``compose._resolve_active_strategies`` and
``compose_answer``). The key value never enters the summary. Only
:func:`build_connection_targets` carries it, for the server's own test
request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings, _resolve_effective_embed_provider

#: The only OpenRouter base URL. It is fixed in the provider builders.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
#: LLM registry providers, in display order.
PROVIDERS: tuple[str, ...] = ("ollama", "llamacpp", "openrouter")
#: Metadata extraction modes that pick a backend from ``metadata_llm_provider``.
_ALIAS_MODES = frozenset({"llamaindex", "local"})


@dataclass(frozen=True)
class ConnectionTarget:
    """Model-list requests the server sends to test one provider.

    Attributes:
        urls: Full request URLs. Empty means the provider is not configured.
        headers: Request headers. They can hold the key, so they stay out
            of ``repr`` and are never returned to a client.
    """

    urls: tuple[str, ...]
    headers: dict[str, str] = field(default_factory=dict, repr=False)


def _backend(settings: Settings, alias: str) -> str:
    """Resolve the ``cloud`` and ``local`` aliases; other names stay literal."""
    value = (alias or "cloud").strip()
    if value in ("", "cloud"):
        return settings.cloud_backend
    if value == "local":
        return settings.local_backend
    return value


def _metadata_provider(settings: Settings) -> str | None:
    """Return the provider metadata extraction calls, or ``None`` for no LLM call.

    Follows ``core.metadata.extractor``: ``keyword`` and ``disabled`` never
    call a model, ``ollama``, ``llamacpp`` and ``openrouter`` name their
    provider, and ``llamaindex`` and ``local`` resolve the alias.
    """
    mode = settings.metadata.extraction_mode.lower()
    if mode in PROVIDERS:
        return mode
    if mode not in _ALIAS_MODES:
        return None
    if settings.metadata_llm_provider == "cloud":
        return settings.cloud_backend
    return settings.local_backend


def _role_providers(settings: Settings) -> dict[str, str | None]:
    """Return the provider name each role uses, or ``None`` when the role is off."""
    answer = settings.answer
    return {
        "embeddings": _resolve_effective_embed_provider(settings),
        "answers": answer.provider.strip() if answer.enabled else None,
        "metadata": _metadata_provider(settings),
        "verification": (
            _backend(settings, answer.verify_provider)
            if answer.enabled and answer.verify_claims
            else None
        ),
    }


def _models(settings: Settings, provider: str, held: list[str]) -> list[dict[str, str]]:
    embeddings, chat = {
        "ollama": (settings.embed_model, settings.metadata.ollama_classify_model),
        "llamacpp": (settings.llamacpp_embed_model, settings.llamacpp_chat_model),
        "openrouter": (settings.openrouter_embed_model, settings.openrouter_llm_model),
    }[provider]
    models = [{"label": "embeddings", "name": embeddings}, {"label": "chat", "name": chat}]
    if "answers" in held:
        models.append({"label": "answers", "name": settings.answer.model})
    if "verification" in held and settings.answer.verify_model:
        models.append({"label": "verification", "name": settings.answer.verify_model})
    return models


def _urls(settings: Settings, provider: str) -> list[dict[str, str]]:
    if provider == "ollama":
        return [{"label": "base", "url": settings.ollama_base_url}]
    if provider == "llamacpp":
        return [
            {"label": "embeddings", "url": settings.llamacpp_embed_url},
            {"label": "chat", "url": settings.llamacpp_chat_url},
        ]
    return [{"label": "base", "url": OPENROUTER_BASE_URL}]


def build_connection_summary(settings: Settings, config_dir: Path) -> dict[str, Any]:
    """Return the provider summary for ``GET /v1/connections``.

    Args:
        settings: Resolved settings.
        config_dir: The working directory whose ``.env`` the settings read.

    Returns:
        ``{"config_dir": str, "connections": [entry, ...]}``. Each entry has
        ``provider``, ``urls``, ``models``, ``key_set`` and ``roles``. The
        key value is never included.
    """
    by_role = _role_providers(settings)
    entries = []
    for provider in PROVIDERS:
        held = [role for role, name in by_role.items() if name == provider]
        entries.append(
            {
                "provider": provider,
                "urls": _urls(settings, provider),
                "models": _models(settings, provider, held),
                "key_set": bool(settings.openrouter_api_key) if provider == "openrouter" else False,
                "roles": held,
            }
        )
    return {"config_dir": str(config_dir), "connections": entries}


def _join(base: str, path: str) -> tuple[str, ...]:
    base = base.strip().rstrip("/")
    return (f"{base}{path}",) if base else ()


def build_connection_targets(settings: Settings) -> dict[str, ConnectionTarget]:
    """Return the model-list request each provider test sends.

    Ollama ``GET /api/tags``, llama.cpp ``GET /models`` on each configured
    URL, OpenRouter ``GET /models`` with the key. OpenRouter without a key
    has no URL, so the test reports ``not-configured`` and sends nothing.
    """
    key = settings.openrouter_api_key.strip()
    llamacpp = (
        *_join(settings.llamacpp_embed_url, "/models"),
        *_join(settings.llamacpp_chat_url, "/models"),
    )
    return {
        "ollama": ConnectionTarget(_join(settings.ollama_base_url, "/api/tags")),
        "llamacpp": ConnectionTarget(tuple(dict.fromkeys(llamacpp))),
        "openrouter": ConnectionTarget(
            _join(OPENROUTER_BASE_URL, "/models") if key else (),
            {"Authorization": f"Bearer {key}"} if key else {},
        ),
    }
