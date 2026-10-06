"""Where the dots-mocr engine keeps its model files (design D8)."""

from __future__ import annotations

from pathlib import Path

from omrg_ocr_worker_core.engine import model_cache_dir

ENGINE_NAME = "dots-mocr"

#: The engine project folder. The engine is installed editable by
#: ``uv sync`` (it is the root project of its folder), so ``__file__``
#: resolves inside ``engines/dots-mocr/src/``.
ENGINE_DIR = Path(__file__).resolve().parents[2]

#: Upstream warns against periods in the model folder name: the folder
#: name becomes part of a dynamic Python module name.
MODEL_FOLDER = "DotsMOCR"


def cache_dir() -> Path:
    """Return the engine's cache root (``HF_HOME`` points here too)."""
    return model_cache_dir(ENGINE_NAME, ENGINE_DIR)


def model_dir() -> Path:
    """Return the folder that holds the pinned, patched model files."""
    return cache_dir() / MODEL_FOLDER
