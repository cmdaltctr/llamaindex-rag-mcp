"""Offline Hugging Face tokenizer loading for chunk-size calculation."""

from __future__ import annotations

from functools import lru_cache

from huggingface_hub import try_to_load_from_cache
from tokenizers import Tokenizer


class TokenizerUnavailableError(RuntimeError):
    """Raised when a configured tokenizer is absent from the local cache."""


@lru_cache(maxsize=8)
def load_tokenizer(model: str, revision: str) -> Tokenizer:
    """Load one tokenizer revision without contacting Hugging Face Hub.

    Args:
        model: Hugging Face tokenizer repository identity.
        revision: Repository revision or commit identifier.

    Returns:
        A cached tokenizer with truncation disabled.

    Raises:
        TokenizerUnavailableError: If ``tokenizer.json`` is not cached.
    """
    cached_path = try_to_load_from_cache(
        repo_id=model,
        filename="tokenizer.json",
        revision=revision,
    )
    if not isinstance(cached_path, str):
        raise TokenizerUnavailableError(
            f"Tokenizer '{model}' revision '{revision}' has no tokenizer.json "
            "in the local Hugging Face cache. Cache it before ingestion."
        )

    tokenizer = Tokenizer.from_file(cached_path)
    tokenizer.no_truncation()
    return tokenizer
