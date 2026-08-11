"""Shared helpers for reading HuggingFace model config values.

The ``tokenizers`` package does not expose ``model_max_length`` or pad
token configuration the way ``transformers.AutoTokenizer`` did.  These
helpers fetch the values from ``config.json`` and ``tokenizer_config.json``
on the HuggingFace snapshot, with graceful fallbacks.

Imported by ``reranker.py`` (ONNX backend) and ``reranker_torch.py``
(torch backend) so both honour the model's own limits.
"""

from __future__ import annotations

import json
import os

# Fallback when the model's config.json is unavailable or lacks the key.
# Mirrors ``TOKENIZER_MAX_LENGTH`` in ``reranker.py`` — kept as a local
# constant to avoid a circular import (``reranker.py`` imports from here).
_DEFAULT_MAX_LENGTH = int(os.getenv("RERANK_TOKENIZER_MAX_LENGTH", "2048"))


def read_max_position_embeddings(model_id: str) -> int:
    """Read ``max_position_embeddings`` from the model's ``config.json``.

    Falls back to the configured default when the file is absent, the
    key is missing, or the value is an implausible sentinel.

    Args:
        model_id: HuggingFace model ID.

    Returns:
        The model's maximum sequence length, or the configured default.
    """
    try:
        from huggingface_hub import hf_hub_download

        config_path = hf_hub_download(repo_id=model_id, filename="config.json")
        with open(config_path) as f:
            config = json.load(f)
        model_max = config.get("max_position_embeddings")
        if not isinstance(model_max, int) or model_max > 100000:
            return _DEFAULT_MAX_LENGTH
        return model_max
    except Exception:
        return _DEFAULT_MAX_LENGTH


def read_pad_token_config(model_id: str) -> tuple[int | None, str | None]:
    """Read ``pad_token_id`` and ``pad_token`` from the model's config.

    The ``tokenizers`` library's ``enable_padding()`` defaults to
    ``pad_id=0`` and ``pad_token="[PAD]"``, which are correct for
    BERT-family models but wrong for others (e.g. RoBERTa uses
    ``pad_token_id=1`` and ``pad_token="<pad>"``).  This reads
    ``pad_token_id`` from ``config.json`` and ``pad_token`` from
    ``tokenizer_config.json`` so padding uses the model's own values.

    Falls back to ``(None, None)`` when either file or key is absent —
    the caller passes these to ``enable_padding()`` which treats
    ``None`` as "use library default".

    Args:
        model_id: HuggingFace model ID.

    Returns:
        ``(pad_token_id, pad_token)`` from the model config, or
        ``(None, None)`` when unavailable.
    """
    try:
        from huggingface_hub import hf_hub_download

        pad_id: int | None = None
        pad_token: str | None = None

        config_path = hf_hub_download(repo_id=model_id, filename="config.json")
        with open(config_path) as f:
            config = json.load(f)
        raw_pad_id = config.get("pad_token_id")
        if isinstance(raw_pad_id, int):
            pad_id = raw_pad_id

        try:
            tc_path = hf_hub_download(repo_id=model_id, filename="tokenizer_config.json")
            with open(tc_path) as f:
                tc = json.load(f)
            raw_pad_token = tc.get("pad_token")
            if isinstance(raw_pad_token, str):
                pad_token = raw_pad_token
        except Exception:  # noqa: S110
            pass  # tokenizer_config.json is not always present

        return pad_id, pad_token
    except Exception:
        return None, None
