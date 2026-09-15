# Design: Experiment 33 Full OMRG Document RAG Benchmark

## Status

DRAFT. The benchmark must not begin measured execution until the open questions are resolved and the protocol is frozen.

## Context

OMRG now has evidence for individual stages but no single benchmark that exercises the current document path as one system. Experiment 33 should become the reference baseline for current OMRG before external framework comparisons are attempted.

## Goals

- Evaluate the current OMRG document pipeline end to end on realistic PDFs.
- Separate ingestion/parser failures from chunking, retrieval, reranking, and answer-stage failures.
- Record quality, latency, and resource/cost signals in one reproducible run.
- Produce a baseline suitable for later comparison with other RAG frameworks.

## Non-Goals

- Do not compare against historical OMRG.
- Do not compare against LlamaIndex, Haystack, or LangChain in Experiment 33.
- Do not tune production defaults on the measured test set.
- Do not change embedding models, rerankers, OCR thresholds, or chunking settings during held-out scoring.

## Pipeline Under Test

The primary arm should use the current `documents` profile and current production-capable configuration:

`raw PDF -> PDF reader/routing -> reader rescue or OCR when required -> Markdown interface -> token-aware chunking -> embedding -> LanceDB -> retrieval -> reranker -> grounded answer`

The exact provider/model identities must be frozen in the final protocol and recorded in every runtime manifest.

## Measurement Layers

### Layer 1: source evidence recovery

Determine whether gold evidence is present in the reader/OCR output before chunking.

### Layer 2: chunk preservation

Determine whether recovered gold evidence survives chunking in retrievable chunks.

### Layer 3: retrieval and reranking

Measure Evidence Recall@1, @3, @5, and @10, MRR@10, nDCG@10 where qrels support it, and no-hit rate.

### Layer 4: grounded answer

If included in the final protocol, score answer correctness and grounding/citation faithfulness on datasets with usable gold answers. The judge/model and scoring method remain open decisions.

### Layer 5: operational measurements

Record ingestion wall time, OCR work, embedding request tokens, chunk count, index size, and query latency including p50/p95 where sample size supports it.

## Candidate Corpus

Current candidates:

1. MMLongBench-Doc-V2 for long and visually complex PDFs.
2. FinanceBench for reports, tables, and numerical evidence.
3. A reproducible QASPER PDF subset for academic papers.
4. An OMRG pathology set for scans, mixed PDFs, legacy font failures, and known extraction pathologies.

This list is a draft. The final benchmark must define exact versions, source URLs, licences, file hashes, inclusion rules, and weighting before execution.

## Validity Controls

- Freeze corpus, queries, qrels/gold answers, scoring code, and query order before measured execution.
- Freeze effective OMRG settings and all model/provider identities.
- Record repository SHA and dependency-lock hashes.
- Record index-shaping identities separately from query-time identities.
- Do not tune on the measured test partition.
- Preserve failures and missing outputs; do not silently drop difficult documents or queries.
- Publish enough non-sensitive artefact identity to reproduce the run.

## Draft Open Questions

1. Which corpus combination is the primary benchmark, and how are datasets weighted?
2. Is QASPER included in the first run or deferred?
3. What is the minimum pathology-set composition without overfitting to known failures?
4. Which embedding provider/model is the reference configuration for the first baseline?
5. Is grounded-answer scoring mandatory in Experiment 33 or a secondary subset?
6. Which answer-quality metric or judge is acceptable if answer scoring is included?
7. What practical success gates, if any, should be frozen before the first baseline?
8. What runtime and paid-provider budget is acceptable?
9. Should worker-less graceful degradation be a secondary operational arm or a separate experiment?

## Decision Rule

Experiment 33 establishes a baseline. It does not need to prove superiority over another system.

The final report should state where OMRG is strong, where evidence is lost, and which bottleneck deserves the next experiment. Any production change requires its own proposal and evidence path.
