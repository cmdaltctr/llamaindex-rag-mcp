"""Path setup for the Experiment 5b fast harness tests.

Puts the experiment directory (top-level modules such as
``protocol_frames`` and ``ipc_client``) and the repository root (the
``experiments`` package and ``experiments._lib``) on ``sys.path`` so the
suite runs under the registered invocation:

    PYTHONPATH=../..:. uv run --no-sync pytest tests/ -q
"""

from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()

# Experiment directory: 5b-persistent-mps-reranker-worker-2026-08-20/
sys.path.insert(0, str(_HERE.parent.parent))
# Repository root: parent of the ``experiments`` package.
sys.path.insert(0, str(_HERE.parents[3]))
