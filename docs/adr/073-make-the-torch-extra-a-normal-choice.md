# ADR-073: Make the Optional `torch` Extra a Normal Choice

**Date:** 2026-10-08
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Related:** [ADR-005](005-cross-encoder-reranker-with-onnx-runtime.md), [ADR-038](038-pluggable-reranker-backend.md)
**Evidence:** `experiments/38-rescue-quality-signal-2026-09-30/report.md`

## Context

Since ADR-005 the project rule was: never PyTorch in the base install or on the default retrieval path. PyTorch behind the optional `torch` extra needed operator approval each time (Ask).

The approval step now slows AI work. In Experiment 38 the yes/no parity check for Julia 1 stayed unverified, because the publisher's reference needs PyTorch. We also ran every decision model in its own isolated environment, to avoid asking each time.

The reasons for keeping torch out of the base install have not changed. They rest on measured speed and install size (ADR-005, 038, 041, 043) and on a past case where a transitive dependency pulled torch into the default install unnoticed.

## Decision

1. PyTorch stays out of the base install and off the default retrieval path. This is unchanged.
2. The optional `torch` extra becomes a normal choice. Installing it (`uv sync --extra torch`) and running experiments, parity checks or evaluation tools on it SHALL NOT need operator approval.
3. Adding `torch`, or a package that pulls it in, to the core dependencies stays an operator decision, like any core dependency.
4. CI is unchanged. The check "default install is torch-free", the runtime tests in `tests/test_no_torch_at_runtime.py` and the `torch-extra` job all remain.

## Consequences

- `pyproject.toml`, CI, the specs and the install size are unchanged.
- Experiments that need PyTorch can use the extra in the project environment. They no longer need a separate environment only to avoid the rule.
- A transitive dependency that brings torch into the base install still fails CI.

## Alternatives considered

1. **Allow torch in the base install** (keep it off the default retrieval path only). Rejected for now. It removes the install-level CI check and gains nothing today, because no feature imports torch by default. Reopen this if one does.
2. **Remove the rule entirely.** Rejected. The default retrieval path is measured on ONNX, and the reranker ADRs stand.
