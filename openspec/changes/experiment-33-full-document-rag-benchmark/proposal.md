# Experiment 33: Full OMRG Document RAG Benchmark

> Status: DRAFT. Do not execute the measured benchmark until the open questions in `design.md` are resolved and approved.

## Why

OMRG has component-level evidence for OCR recovery, routing, token-aware chunking, query preparation, reader rescue, and retrieval choices. It does not yet have one full evaluation of the current document pipeline as a complete RAG system.

The next major evidence step should establish a reproducible quality and cost baseline for current OMRG itself. Historical OMRG comparisons are out of scope. Framework comparisons against LlamaIndex, Haystack, or other systems can use this baseline later.

## What Changes

- Draft Experiment 33 as a full current-system document RAG benchmark.
- Exercise the current `documents` profile from raw PDF ingestion through retrieval, reranking, and grounded answering where the chosen benchmark supports answer scoring.
- Freeze the final benchmark corpus, queries, qrels/gold answers, effective settings, model identities, and scoring rules before measured execution.
- Measure retrieval quality as the primary diagnostic layer.
- Measure parser evidence recovery, chunk coverage, OCR behaviour, ingestion cost, index size, and query latency.
- Score answer correctness and grounding on an approved subset if the final protocol includes answer synthesis.
- Keep external framework comparisons out of Experiment 33.
- Do not change production defaults from this draft.

## Candidate Benchmark Corpus

The current shortlist is intentionally not final:

- MMLongBench-Doc-V2;
- FinanceBench;
- a reproducible QASPER PDF subset;
- an OMRG pathology set covering known parser/OCR failure classes.

The final mix, licences, download procedure, sample size, and weighting remain open decisions.

## Capabilities

### New Capabilities

- `document-rag-evaluation`: defines the reproducibility and measurement contract for a full current OMRG document-RAG benchmark.

### Modified Capabilities

- None.

## Impact

- Draft-only experiment governance until the protocol is approved.
- No production code, public API, or packaged default changes.
- The resulting baseline can later support controlled comparisons with LlamaIndex, Haystack, or other frameworks.
