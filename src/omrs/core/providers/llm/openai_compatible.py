"""OpenAI-compatible LLM provider (Chat answers only).

Constructs an ``OpenAILike`` LLM pointed at any server that speaks the
OpenAI chat API: OpenAI itself, LM Studio, vLLM, Together and similar. The
address and the optional key come from settings. A local server needs no
key, so the key is optional. Requires ``llama-index-llms-openai-like``,
which is in the base install.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
    join_url,
    models_from,
)

if TYPE_CHECKING:
    from ....config import Settings

#: The client refuses an empty key, so a keyless server gets this placeholder.
_NO_KEY = "no-key"


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
) -> Any:
    """Construct an ``OpenAILike`` chat LLM for the saved address from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the answer composition root
            passes ``answer.timeout``.
        answer_model: The model name. This provider has no model setting of
            its own, so the Chat model is required.

    Returns:
        A configured ``OpenAILike`` LLM.

    Raises:
        ValueError: *answer_model* is missing or blank.
    """
    from llama_index.llms.openai_like import OpenAILike

    if not (answer_model or "").strip():
        raise ValueError("The OpenAI-compatible provider needs a Chat model name.")
    return OpenAILike(
        model=answer_model,
        api_base=settings.openai_compatible_base_url,
        api_key=settings.openai_compatible_api_key.strip() or _NO_KEY,
        is_chat_model=True,
        # OpenAILike names this ``timeout``; ``request_timeout`` is the Ollama
        # spelling and is silently dropped, leaving the 60s default in place.
        timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
    )


def _models_target(settings: Any) -> ConnectionTarget:
    """Return ``GET {address}/models``, with a bearer header only when a key is set.

    The key goes to this provider's address and nowhere else.
    """
    urls = join_url(settings.openai_compatible_base_url, "/models")
    key = settings.openai_compatible_api_key.strip()
    return ConnectionTarget(urls, {"Authorization": f"Bearer {key}"} if key and urls else {})


#: Card data for the OpenAI-compatible provider (design D5).
CONNECTION = ConnectionDescriptor(
    display_name="OpenAI-compatible",
    locality="cloud",
    requires_module="llama_index.llms.openai_like",
    extra=None,
    fields=(
        ConnectionField(
            "base_url",
            "Address",
            "url",
            "openai_compatible_base_url",
            "OPENAI_COMPATIBLE_BASE_URL",
        ),
        ConnectionField(
            "api_key",
            "API key",
            "secret",
            "openai_compatible_api_key",
            "OPENAI_COMPATIBLE_API_KEY",
            required=False,
        ),
    ),
    read_only=lambda s: [],
    test_targets=_models_target,
    models_target=_models_target,
    parse_models=lambda payload: models_from(payload, "data", "id"),
)
