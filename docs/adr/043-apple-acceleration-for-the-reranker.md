# ADR-043: Apple Acceleration for the Reranker

**Date:** 2026-08-13
**Status:** Accepted
**Scopes:** ADR-005 (no PyTorch on the default path — unchanged), ADR-029 (silent fallback lesson — reinforced), ADR-038 (pluggable reranker backend — measured)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The project's default reranker runs `cross-encoder/ms-marco-MiniLM-L-6-v2` through
ONNX Runtime on CPU (ADR-005). ADR-038 made Apple MPS reachable through the optional
torch reranker backend (`SentenceTransformerReranker`), but recorded no measured
evidence for its value. Two acceleration routes exist on Apple Silicon:

1. **ONNX CoreML EP** — tested in Experiment 16 on `gte-reranker-modernbert-base`.
   CoreML is 2.3x slower than int8 CPU (5393 ms vs 2348 ms P50). CoreML cannot
   handle the dynamic sequence lengths that cross-encoder batching produces.
   Conclusion: dead for this model family.

2. **PyTorch MPS** — accessible through the torch backend (ADR-038). Sentence
   Transformers 5 auto-selects MPS when `device` is omitted. No measured evidence
   existed for this route on the production MiniLM model. This ADR fills that gap.

The project needs a hardware-specific verdict: does MPS help the reranker enough
to justify a runtime code change, or should ONNX CPU remain the default?

## Decision

**Keep ONNX CPU as the default reranker backend. Do not promote MPS to the
production path.**

MPS is technically excellent (4.5x faster on MiniLM) but adoption is blocked
by a ranking-consistency gate: ONNX int8 and torch fp32 produce different
rankings on near-tied documents. Changing the default backend would silently
alter retrieval results for users whose queries produce close-scoring documents.

The torch backend retains Sentence Transformers' automatic MPS device selection
for opt-in use (`RETRIEVAL__RERANK_BACKEND=torch`). No runtime code or
configuration change is needed for opt-in MPS.

### Technical MPS verdict: positive

Experiment 17 measured three cells on `cross-encoder/ms-marco-MiniLM-L-6-v2`
with a fixed 5-query x 20-document workload:

| Gate | Result | Evidence |
| --- | :---: | --- |
| H1 — MPS usable | PASS | 17C loaded, selected MPS, completed without CPU fallback (`PYTORCH_ENABLE_MPS_FALLBACK=0`) |
| H2 — MPS accelerates torch | PASS | 17C P50 54.9 ms <= 0.8 x 17B P50 243.3 ms (4.4x improvement) |
| H3 — MPS beats ONNX CPU | PASS | 17C P50 54.9 ms <= 0.8 x 17A P50 245.3 ms; 17C P95 193.4 ms <= 17A P95 497.9 ms |
| H4 — operational cost bounded | PASS | Cold start 3.9 s (2.9x baseline); peak RSS 568.4 MB (1.54x baseline) |

MPS current-allocated memory: 86.7 MB. Driver-allocated: 1056.7 MB (driver
reserves headroom that PyTorch does not actively use for this model size).

The preflight confirmed that `SentenceTransformerReranker` (production
constructor, no device override) auto-selects MPS on this hardware.

### Project adoption verdict: negative

| Gate | Result | Evidence |
| --- | :---: | --- |
| H5 — ranking consistency | FAIL | ONNX int8 rankings differ from torch fp32 on 2 of 5 queries |

The H5 failure is **not** an MPS device issue. Cell 17B (torch CPU) and cell
17C (torch MPS) produce identical rankings on all 5 queries. The divergence is
between ONNX int8 (`model_qint8_arm64.onnx`) and torch fp32 weights: the two
queries where rankings differ have documents with sub-1% score margins, where
the quantization precision difference is large enough to flip the order.

The project's score-parity contract (ADR-038, design decision 7) requires
backends to produce comparable scores. While the sigmoid-parity contract test
enforces score range, the MiniLM workload shows that int8 quantization can
reorder near-tied documents. Changing the default backend would silently alter
retrieval results.

## Evidence summary

### Experiment 16 (CoreML, ModernBERT)

Source: `experiments/16-reranker-coreml-fp16-2026-08-03/results.md`

CoreML EP is 2.3x slower than int8 CPU on `gte-reranker-modernbert-base`
(5393 ms vs 2348 ms P50). CoreML cannot handle dynamic sequence lengths.
CoreML is dead for cross-encoder models.

### Experiment 17 (MPS, MiniLM)

Source: `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/results.md`

| Cell | Backend | Device | P50 (ms) | P95 (ms) | Cold (s) | RSS (MB) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 17A | ONNX (int8 arm64) | CPU | 245.3 | 497.9 | 1.4 | 368.6 |
| 17B | torch (fp32) | CPU | 243.3 | 475.9 | 3.7 | 590.5 |
| 17C | torch (fp32) | MPS | 54.9 | 193.4 | 3.9 | 568.4 |

Rankings: 17B == 17C on all queries. 17A != 17C on queries 1 and 5.

## Fallback policy

`PYTORCH_ENABLE_MPS_FALLBACK=0` must be set before torch import in any process
that uses the torch reranker backend. This prevents silent CPU fallback when
MPS encounters an unsupported operation. If MPS cannot handle an op, the
process fails loudly rather than reporting CPU performance as MPS performance.

This policy reinforces the ADR-029 lesson: silent fallbacks are worse than
failures because they create invisible performance and accuracy regressions.

## Conditions that require re-testing

1. **Production corpus test.** This experiment uses a synthetic workload that
   amplifies ranking sensitivity (near-identical documents create sub-1% score
   margins). A production corpus with wider score margins may not exhibit H5
   failure. If such a test passes H5, revisit this decision.

2. **ONNX fp32 isolation.** Testing the ONNX fp32 variant (`model.onnx`) would
   isolate whether the ranking divergence is purely int8 quantization or also
   involves tokenisation differences between `tokenizers` and `transformers`.
   If fp32 ONNX rankings match torch fp32, the int8 variant is the sole cause.

3. **ORT CoreML dynamic shapes.** If a future ORT version fixes the
   dynamic-shape crash (Experiment 16), ONNX fp32 on Apple GPU becomes viable
   without the torch dependency. Re-test CoreML with MiniLM.

4. **Hardware generation change.** Results apply to Apple M1 Pro (32 GB).
   Future Apple Silicon generations may change the speed or memory trade-off.

## Consequences

### Positive

- The MPS route is measured and documented. No future "should we try MPS?"
   question needs an exploratory experiment.
- MPS is confirmed as technically viable for opt-in use: users who set
   `RETRIEVAL__RERANK_BACKEND=torch` get automatic MPS acceleration without
   any code change.
- The ranking-consistency finding (int8 vs fp32) is valuable independently:
   it informs any future backend swap decision.

### Negative

- The 4.5x latency improvement from MPS is not captured on the default path.
   Users who need maximum reranker speed must opt in to the torch backend.
- The torch backend can rot from disuse. Its dedicated CI job (ADR-038 task
   11.5) mitigates this.

### Neutral

- The default remains ONNX int8 on CPU. No runtime code or configuration
   changes.
- The torch model cache key has no device axis. If a future change adds
   explicit device configuration, the cache key must include device to avoid
   returning a CPU model when MPS was requested.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Promote MPS to default despite H5 failure | Silently alters retrieval results; violates the score-parity contract |
| Test ONNX fp32 to isolate int8 cause | Out of scope for this change; recorded as a re-test condition |
| Add `auto\|cpu\|mps` device configuration now | Premature — H5 failure blocks adoption regardless of device config |
| Remove the torch backend since MPS is not adopted | MPS is viable for opt-in use; the backend serves users who accept the ranking trade-off |

## References

- `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/results.md` — full results
- `experiments/16-reranker-coreml-fp16-2026-08-03/results.md` — CoreML evidence
- ADR-005 — original ONNX-only reranker decision
- ADR-029 — silent fallback lesson (CoreML)
- ADR-038 — pluggable reranker backend (torch backend)
- `src/rag_mcp/core/retrieval/reranker.py` — ONNX backend (default)
- `src/rag_mcp/core/retrieval/reranker_torch.py` — torch backend (opt-in)
