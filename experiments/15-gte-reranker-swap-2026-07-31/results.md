# Experiment 15: gte-reranker-modernbert-base A/B Comparison

**Recommendation:** REJECT — gte does not beat rerank-off baseline. Both rerankers degrade technical retrieval.

**Status:** INCONCLUSIVE (small sample + reduced candidate pool; see caveats)

## Executive summary

The gte-reranker-modernbert-base (149M params) was tested against the rerank-off
baseline and the current MiniLM default on FreshStack LangChain (30-query subset,
reduced candidate pool of 30). **Both rerankers degrade retrieval quality on this
identifier-heavy corpus.** The gte model is less harmful than MiniLM (+4.2pp
Coverage@20) but still 16.1pp below the rerank-off baseline. Latency on CPU is
impractical (24.6s P95 per query).

**Critical discovery:** During this experiment, two bugs were found that mean
**all prior reranker experiments (Exp 10, 12) were testing a broken reranker**:
1. CoreML execution provider silently failed on every inference (dynamic sequence
   lengths unsupported), returning un-reranked fallback results.
2. The `max_length=2048` change exceeded MiniLM's 512-token ONNX position embedding
   limit, causing broadcast errors.

Both bugs are now fixed in `reranker.py`. The MiniLM degradation results in this
experiment are the **first valid reranker quality measurements** on this corpus.

## Cell metrics (all 30 queries)

| Cell | Reranker | Coverage@20 | Hit@1 | Hit@5 | Hit@10 | MRR@10 | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rerank-off | N/A | **0.5856** | **0.3000** | **0.6000** | **0.7333** | **0.4456** | 39,169* |
| MiniLM | cross-encoder/ms-marco-MiniLM-L-6-v2 | 0.3828 | 0.1000 | 0.4333 | 0.5333 | 0.2220 | 5,015 |
| gte-reranker | Alibaba-NLP/gte-reranker-modernbert-base | 0.4244 | 0.1333 | 0.3333 | 0.5000 | 0.2330 | 24,580 |

\*P95 inflated by BM25 index build on first query. Actual per-query P95 ≈ 500ms (from 223-query run).

## Identifier-heavy subset (29 queries)

| Cell | Coverage@20 | Hit@1 | Hit@5 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| rerank-off | **0.6057** | **0.3103** | **0.6207** | **0.4610** |
| MiniLM | 0.3960 | 0.1034 | 0.4483 | 0.2296 |
| gte-reranker | 0.4046 | 0.1034 | 0.3103 | 0.2066 |

## Pass gates

| Criterion | Value | Threshold | Pass? |
| --- | ---: | ---: | ---: |
| gte beats baseline 0.738 | 0.424 | ≥ 0.738 | ❌ FAIL |
| gte beats rerank-off | 0.424 | ≥ 0.586 | ❌ FAIL |
| gte beats MiniLM | 0.424 | ≥ 0.383 | ✅ PASS |
| Coverage lift ≥ 3pp | -16.1pp | ≥ +3pp | ❌ FAIL |
| Latency ≤ 3× baseline* | 0.63× | ≤ 3.0× | ✅ (misleading*) |

\*The latency gate technically passed because the rerank-off P95 (39s) includes
the one-time BM25 index build. Actual per-query latency ratio is ~24,580ms /
~500ms ≈ **49×**, which massively fails the 3× guardrail.

## Conclusion / decision

**The gte-reranker swap is NOT adopted.** Both rerankers degrade technical
retrieval on FreshStack LangChain. The gte model is marginally better than MiniLM
but still harmful, and its CPU latency (24.6s P95) is impractical.

### What this means for the OpenSpec change

- **ADR-028 status:** Remains Proposed → should be updated to **Rejected**.
- **RERANK_MODEL default:** The code change to `Alibaba-NLP/gte-reranker-modernbert-base`
  should be **reverted** or made opt-in only.
- **RERANK_ENABLED:** Should remain `false` (ADR-019) — no reranker helps on
  identifier-heavy technical corpora.
- **The CoreML and max_length bug fixes ARE valid and should be kept** — they
  fix silent failures that invalidated all prior reranker experiments.

### Caveats and limitations

1. **Small sample (30 queries):** High variance. The 223-query run for cells 1–2
   showed Coverage@20=0.7395 (rerank-off) vs 0.6068 (MiniLM), confirming the
   degradation pattern at scale.
2. **Reduced candidate pool (30 vs 150):** Fewer candidates may limit the
   reranker's ability to surface relevant documents. However, the rerank-off
   baseline used the same pool and achieved higher quality.
3. **max_length=512:** Does not leverage gte's 8,192-token context window. Longer
   context might help on documents with dispersed evidence, but most RAG chunks
   are ≤512 tokens.
4. **CPU-only inference:** The gte model's 149M params make CPU inference
   impractical (~25s/query). GPU/accelerator would be needed for production use.
5. **FreshStack LangChain only:** The corpus is heavily identifier-heavy (200/223
   queries). A semantic-heavy corpus (e.g., Qasper) might show different results.

### Follow-up experiments

1. **Test on a semantic-heavy corpus** (Qasper) where reranking might help.
2. **Test with GPU acceleration** (CoreML fixed, or CUDA) to assess latency.
3. **Re-evaluate ADR-019** with the now-working reranker — the prior "reranker
   degrades" finding was based on a broken implementation.

## Bugs discovered and fixed

### Bug 1: CoreML silent failure (production code)

**Symptom:** Every reranker inference returned un-reranked fallback results.
**Root cause:** CoreML execution provider doesn't support dynamic sequence lengths
produced by cross-encoder tokenisation (variable batch padding).
**Fix:** Default to `CPUExecutionProvider` (`RERANK_ONNX_PROVIDER=cpu`).
**Impact:** Post-ADR-021 reranker experiments (Exp 12, 9a-rerun, 13) had
invalid rerank-on cells. Exp 10 (May 31, pre-ADR-021) was valid — the
reranker ran on CPU and genuinely degraded quality.

### Bug 2: max_length exceeds model limit (introduced by this change)

**Symptom:** ONNX broadcast error: "Attempting to broadcast an axis by a dimension
other than 1. 512 by 2048".
**Root cause:** `TOKENIZER_MAX_LENGTH=2048` exceeded MiniLM's 512-token position
embedding limit.
**Fix:** Cap `max_length` at `tokenizer.model_max_length` per model.

## References

- Exp 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/` (prior MiniLM test — INVALID due to CoreML bug)
- Exp 12: `experiments/12-hybrid-default-promotion-2026-06-29/` (prior hybrid test — reranker cells INVALID)
- ADR-019: Disable Reranker for Technical Workloads
- ADR-021: Reranker Inference Optimisation (÷30 threshold scaling)
- ADR-028: Swap Default Reranker (Rejected — this experiment)
- ADR-029: Disable CoreML for Reranker — Silent Fallback Lesson (Accepted)
- OpenSpec: `openspec/changes/swap-reranker-to-gte-modernbert/`

## Remaining OpenSpec tasks

26 of 35 tasks complete. The 9 remaining tasks and why they are blocked:

| Task | Status | Reason |
| --- | --- | --- |
| 2.4 Evaluate on Qasper | Not done | Only FreshStack LangChain evaluated. Qasper corpus requires index preparation (Exp 14 was planned but never run). |
| 2.8 Record raw logit distributions | Not done | `record_logits.py` timed out — the script used CoreML provider (not yet fixed in the standalone script). Re-run with `RERANK_ONNX_PROVIDER=cpu`. |
| 3.1 Compare logit std devs | Blocked | Depends on 2.8 (logit data not collected). |
| 3.2 Run threshold calibration | Moot | Swap rejected — no need to calibrate thresholds for a model we're not adopting. |
| 3.3 Update `_effective_threshold()` | Moot | Same — recalibration only relevant if gte is adopted. |
| 3.4 Document recalibration results | Moot | Same. |
| 7.1 Update AIE-20 subtasks in NiftyPM | Not done | NiftyPM sync not started. Should reflect rejection, not completion. |
| 7.2 Mark AIE-20 task in NiftyPM | Not done | Same — AIE-20 should be marked as rejected/closed, not completed. |
| 7.3 Update local JSON | Not done | Same. |

**Recommendation:** Close the OpenSpec change as rejected. Sections 3
(threshold recalibration) and 7 (NiftyPM sync) are moot — there is no
point calibrating thresholds or marking AIE-20 as complete for a swap
that the experiment rejected. If a future experiment tests gte on a
semantic-heavy corpus and finds improvement, a new OpenSpec change
should be created fresh.
