## Context

See `proposal.md` — Why. The constraints that shape the approach:

- The pluggable-reranker-backend change (PR #37) landed the torch backend (`core/retrieval/reranker_torch.py`) behind the `torch` optional extra. The backend wraps `sentence_transformers.CrossEncoder` and applies the same sigmoid normalisation as the ONNX backend, so scores are comparable.
- Experiment 16 (2026-08-03) settled CoreML: fp16 + CoreML at 5393 ms P50 against fp16 + CPU at 5670 ms — no acceleration, because ONNX Runtime partitions the graph and most operations fall back to CPU. int8 + CPU won at 2348 ms. CoreML is NOT re-tested here.
- Experiment 16 used the ModernBERT model (`Alibaba-NLP/gte-multilingual-reranker-base`). This experiment uses the **default MiniLM model** (`cross-encoder/ms-marco-MiniLM-L-6-v2`), so Experiment 16's absolute numbers are not a valid baseline. The comparison is internal: 17A vs 17B vs 17C.
- Experiment 16 finding 4: loading int8 first corrupts ORT's global optimiser state and poisons later cells in the same process. Each cell MUST run in a separate process.

## Goals / Non-Goals

**Goals:**

- Measure MPS (Metal Performance Shaders, accessed via PyTorch's MPS backend) against the ONNX CPU baseline on the default model.
- Record the verdict in ADR-043 so the Apple-acceleration question stops recurring.
- State plainly that CoreML did not fail because PyTorch was absent — it failed because ORT partitions the graph. Give the evidence.
- State accurately that MPS is an Apple framework, not a PyTorch feature. PyTorch's MPS backend is one of several ways to reach it (MPSGraph, Core ML, TensorFlow Metal plugin, MLX, direct Metal kernels). For this project's reranker, the torch backend is the path that makes MPS reachable.

**Non-Goals:**

- Changing the default backend or execution provider. Any default change is a follow-up change with its own ADR.
- Re-testing CoreML. Experiment 16 settled it.
- Benchmarking the ModernBERT model. Experiment 16 covered it. This experiment is about the default model only.
- Code changes to the reranker backends. This is research + an ADR.

## Decisions

### 1. Three cells, separate processes, default model

17A (ONNX int8 CPU), 17B (torch CPU), 17C (torch MPS). Each in a separate process per Experiment 16 finding 4. All on `cross-encoder/ms-marco-MiniLM-L-6-v2` — the default reranker model — so the result answers the question for the default install, not just for a model nobody runs.

### 2. Pass gates stated before running

H1 — torch on MPS loads without error. H2 — 17C P50 latency beats 17A P50 by at least 20%. H3 — 17C cold start no worse than 3× 17A. H4 — 17C top-ranked document matches 17A on every workload query.

The 20% threshold is the minimum that would justify the complexity of a torch device selection change. Anything less is noise.

### 3. ADR records all three routes, not just the winner

ADR-043 covers CoreML (closed by Exp 16), CPU (current default), and MPS (decided by Exp 17). The question "why not X?" is answered for all three values of X. This is what stops the question from recurring — a partial ADR that only covers the winner invites someone to ask about the losers next month.

### 4. No default change in this change

If MPS wins, a follow-up change handles torch device selection (`RETRIEVAL__RERANK_DEVICE=cpu|mps` or similar). This change only measures and records. Mixing measurement with a default switch is how defaults get changed on incomplete evidence.
