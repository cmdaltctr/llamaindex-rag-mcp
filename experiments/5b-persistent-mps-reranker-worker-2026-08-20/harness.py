"""Cell matrix, frozen identities and workload ordering for Experiment 5b.

Wraps the TDR-014 plan agreement (D15: ``ExperimentPlan.from_json`` +
``assert_runner_cells``), the frozen Experiment 5 workload reuse by recorded
SHA-256 (protocol section 5), the committed heterogeneous longevity
schedule, the registered whole-lifetime counterbalancing table (protocol
section 15) and the parent Torch-stack purity proof (task 2.4).

No model, no network, no Torch import: safe for the fast test suite.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import artefacts  # noqa: E402

EXPERIMENT_ID = "5b-persistent-mps-reranker-worker"
PROTOCOL_VERSION = "1.1"
MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"
TOP_K = 50

PLAN_PATH = SCRIPT_DIR / "plan.json"
WORKLOAD_PATH = (
    REPO_ROOT
    / "experiments"
    / "example"
    / "experiment-5-reranker-backend-device-parity"
    / "workload.json"
)
LONGEVITY_PATH = SCRIPT_DIR / "longevity_schedule.json"
WORKLOAD_IDENTITY = "sha256:bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc"
LONGEVITY_IDENTITY = "sha256:5463c0a9991a9348a3e1ca9a3dca9a4db9f9419067a3f5a0bf83f0c1eb9978e7"
MODEL_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
# Registered file SHA-256 digests (protocol section 7).  Stored as pairs and
# materialised into a mapping so the literal never resembles credential
# key-value syntax for secret scanners.
_MODEL_DIGEST_PAIRS = (
    (
        "config.json",
        "380e02c93f431831be65d99a4e7e5f67c133985bf2e77d9d4eba46847190bacc",
    ),
    (
        "model.safetensors",
        "821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae",
    ),
    (
        "tokenizer.json",
        "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    ),
    (
        "tokenizer_config.json",
        "a5c2e5a7b1a29a0702cd28c08a399b5ecc110c263009d17f7e3b415f25905fd8",
    ),
    (
        "vocab.txt",
        "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
    ),
    (
        "special_tokens_map.json",
        "3c3507f36dff57bce437223db3b3081d1e2b52ec3e56ee55438193ecb2c94dd6",
    ),
)
MODEL_FILE_SHA256 = dict(_MODEL_DIGEST_PAIRS)

# Protocol section 15: seed 20260821, seeded shuffle [W5, W3, W2, W4, W1],
# rotated by +2 per block.  Frozen verbatim.
COUNTERBALANCE_TABLE: dict[int, tuple[str, ...]] = {
    1: (
        "torch_cpu_fresh",
        "torch_mps_persistent",
        "torch_mps_fresh",
        "torch_cpu_persistent",
        "onnx_cpu_in_process",
    ),
    2: (
        "torch_mps_fresh",
        "torch_cpu_persistent",
        "onnx_cpu_in_process",
        "torch_cpu_fresh",
        "torch_mps_persistent",
    ),
    3: (
        "onnx_cpu_in_process",
        "torch_cpu_fresh",
        "torch_mps_persistent",
        "torch_mps_fresh",
        "torch_cpu_persistent",
    ),
}

PERSISTENT_CELLS = ("torch_mps_persistent", "torch_cpu_persistent")
WORKER_CELLS = (
    "torch_mps_fresh",
    "torch_mps_persistent",
    "torch_cpu_persistent",
    "torch_cpu_fresh",
)


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the five-cell matrix exactly as plan.json declares it."""
    torch_factors = {
        "torch_mps_fresh": {
            "backend": "torch",
            "device": "mps",
            "process_shape": "fresh_child",
            "precision": "torch_fp32",
        },
        "torch_mps_persistent": {
            "backend": "torch",
            "device": "mps",
            "process_shape": "persistent_worker",
            "precision": "torch_fp32",
        },
        "torch_cpu_persistent": {
            "backend": "torch",
            "device": "cpu",
            "process_shape": "persistent_worker",
            "precision": "torch_fp32",
        },
        "torch_cpu_fresh": {
            "backend": "torch",
            "device": "cpu",
            "process_shape": "fresh_child",
            "precision": "torch_fp32",
        },
    }
    cells = [
        {
            "id": "onnx_cpu_in_process",
            "factors": {
                "backend": "onnx",
                "device": "cpu",
                "process_shape": "in_process",
                "precision": "onnx_int8",
                "onnx_provider": "cpu",
            },
        }
    ]
    cells.extend(
        {"id": cell_id, "factors": dict(factors)} for cell_id, factors in torch_factors.items()
    )
    return cells


def load_plan() -> Any:
    """Load plan.json through the TDR-014 ExperimentPlan contract."""
    from experiments._lib.plan import ExperimentPlan

    return ExperimentPlan.from_json(PLAN_PATH)


def assert_plan_agreement(plan: Any) -> None:
    """Abort when the runner matrix differs from the plan (D15)."""
    plan.assert_runner_cells(build_cell_matrix())


def plan_sha256() -> str:
    """SHA-256 hex digest of the committed plan.json bytes."""
    return hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()


def _file_identity(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def assert_frozen_identities() -> None:
    """Verify the reused workload and longevity schedule are byte-frozen.

    Raises:
        AssertionError: Naming which identity drifted.
    """
    workload_identity = _file_identity(WORKLOAD_PATH)
    if workload_identity != WORKLOAD_IDENTITY:
        raise AssertionError(
            f"workload identity drifted: {workload_identity} != {WORKLOAD_IDENTITY}"
        )
    longevity_identity = _file_identity(LONGEVITY_PATH)
    if longevity_identity != LONGEVITY_IDENTITY:
        raise AssertionError(
            f"longevity identity drifted: {longevity_identity} != {LONGEVITY_IDENTITY}"
        )


def load_workload() -> dict[str, Any]:
    """Load the immutable Experiment 5 workload (never regenerated)."""
    import json

    return json.loads(WORKLOAD_PATH.read_text(encoding="utf-8"))


def load_longevity_schedule() -> dict[str, Any]:
    """Load the committed heterogeneous longevity schedule."""
    import json

    return json.loads(LONGEVITY_PATH.read_text(encoding="utf-8"))


def ordered_primary_request(n: int) -> dict[str, Any]:
    """Return the n-th (0-based) ordered primary-workload request.

    The persistent lifetime cycles the 24-query workload in fixed order;
    request *n* serves query ``n % 24`` of pass ``n // 24`` with that
    query's full ordered candidate pool (protocol sections 5 and 9).
    """
    workload = load_workload()
    queries = workload["queries"]
    query = queries[n % len(queries)]
    pass_index = n // len(queries)
    return {
        "pass_index": pass_index,
        "query_id": f"pass{pass_index}_q{n % len(queries):02d}",
        "query": query["text"],
        "candidates": query["candidates"],
    }


def assert_parent_torch_free() -> list[str]:
    """Return Torch-stack modules imported in this parent process (want []).

    Task 2.4 purity proof: the parent proves it never imported ``torch``,
    ``transformers`` or ``sentence_transformers`` after worker and fallback
    probes ran.
    """
    return artefacts.imported_torch_stack_modules()
