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
import logging

logger = logging.getLogger(__name__)


def read_max_position_embeddings(model_id: str, fallback: int) -> int:
    """Read ``max_position_embeddings`` from the model's ``config.json``.

    Falls back to *fallback* when the file is absent, the key is
    missing, or the value is an implausible sentinel (non-positive,
    a bool, or larger than 100000).

    Args:
        model_id: HuggingFace model ID.
        fallback: Configured default to use when the model's config
            is unavailable or lacks a usable value.

    Returns:
        The model's maximum sequence length, or *fallback*.
    """
    try:
        from huggingface_hub import hf_hub_download

        config_path = hf_hub_download(repo_id=model_id, filename="config.json")
        with open(config_path) as f:
            config = json.load(f)
        model_max = config.get("max_position_embeddings")
        if (
            not isinstance(model_max, int)
            or isinstance(model_max, bool)
            or not (0 < model_max <= 100000)
        ):
            return fallback
        return model_max
    except Exception as exc:
        logger.debug(
            "Could not read max_position_embeddings for %s, using fallback %d: %s",
            model_id,
            fallback,
            exc,
        )
        return fallback


def read_pad_token_config(model_id: str) -> tuple[int | None, str | None]:
    """Read ``pad_token_id`` and ``pad_token`` from the model's config.

    The ``tokenizers`` library's ``enable_padding()`` defaults to
    ``pad_id=0`` and ``pad_token="[PAD]"``, which are correct for
    BERT-family models but wrong for others (e.g. RoBERTa uses
    ``pad_token_id=1`` and ``pad_token="<pad>"``).  This reads
    ``pad_token_id`` from ``config.json`` and ``pad_token`` from
    ``tokenizer_config.json`` so padding uses the model's own values.

    The two values are returned atomically: if either file or key is
    missing, both come back ``None`` rather than a partial pair. A
    partial pair (e.g. ``pad_id=None, pad_token="<pad>"``) would let
    ``enable_padding()`` apply the library's default ``pad_id=0``
    alongside a mismatched token string, which is the exact silent
    mispadding this helper exists to prevent.

    Args:
        model_id: HuggingFace model ID.

    Returns:
        ``(pad_token_id, pad_token)`` from the model config, or
        ``(None, None)`` when either value is unavailable.
    """
    try:
        from huggingface_hub import hf_hub_download

        config_path = hf_hub_download(repo_id=model_id, filename="config.json")
        with open(config_path) as f:
            config = json.load(f)
        raw_pad_id = config.get("pad_token_id")
        pad_id = (
            raw_pad_id
            if isinstance(raw_pad_id, int) and not isinstance(raw_pad_id, bool) and raw_pad_id >= 0
            else None
        )

        tc_path = hf_hub_download(repo_id=model_id, filename="tokenizer_config.json")
        with open(tc_path) as f:
            tc = json.load(f)
        raw_pad_token = tc.get("pad_token")
        pad_token = raw_pad_token if isinstance(raw_pad_token, str) else None

        if pad_id is None or pad_token is None:
            logger.debug(
                "Incomplete pad token config for %s (pad_id=%r, pad_token=%r), "
                "using library defaults",
                model_id,
                pad_id,
                pad_token,
            )
            return None, None
        return pad_id, pad_token
    except Exception as exc:
        logger.debug("Could not read pad token config for %s: %s", model_id, exc)
        return None, None
