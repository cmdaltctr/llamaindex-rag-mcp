# Design: Experiment 34 Local OMRG Profile Baselines

## Status

DRAFT. Measured execution must not begin until both local subsets and the evaluation protocol are frozen.

## Context

OMRG has strong component-level evidence but needs a complete baseline for each primary profile. A large benchmark is premature while the evaluation harness, observability, answer scoring, and cloud deployment path are still being established.

Experiment 34 therefore starts with two small local benchmarks that run sequentially on the operator's Mac.

## Goals

- Evaluate the current `documents` profile end to end on a small real document benchmark.
- Evaluate the current `codebase` profile end to end on a small repository-understanding benchmark.
- Capture stage-level observability so failures can be attributed to the correct pipeline stage.
- Add optional RAGAS evaluation without coupling RAGAS to production OMRG.
- Establish a reproducible local baseline before cloud scale-up.

## Non-Goals

- Do not compare against historical OMRG.
- Do not compare against LlamaIndex, Haystack, LangChain, or other frameworks.
- Do not run a large benchmark locally.
- Do not tune production defaults on the measured subsets.
- Do not add RAGAS, OpenTelemetry, or other evaluation tooling to the base runtime dependency path.

## Execution Order

Run the two baselines separately:

```text
34A FinanceBench / documents
        ↓ complete + report
34B RepoProbe / codebase
        ↓ complete + report
cloud-scale benchmark later
```

The two measured runs must not execute concurrently on the Mac.

## 34A — Document Profile

### Corpus

Use a frozen FinanceBench subset. Initial target: 30–50 questions across multiple source PDFs. The subset should include prose, numerical, and table-backed evidence.

### Pipeline

```text
raw PDF
  -> PDF reader/routing
  -> reader rescue or OCR when required
  -> Markdown interface
  -> token-aware chunking
  -> embedding
  -> LanceDB
  -> documents-profile retrieval
  -> reranker
  -> grounded answer
```

### Primary metrics

- Evidence Recall@1, @3, @5, and @10
- MRR@10
- nDCG@10 when the qrels support it
- no-hit rate

### Diagnostic metrics

- source evidence recoverability after parsing/OCR
- evidence preservation after chunking
- ingestion time
- OCR work and failures
- chunk count
- embedding tokens
- index size
- query latency

## 34B — Codebase Profile

### Corpus

Use a frozen RepoProbe subset. Initial target: two pinned repositories and approximately 10–20 questions total. Freeze repository commit SHAs and question IDs before measured execution.

### Pipeline

```text
pinned repository
  -> current codebase ingestion/chunking
  -> embedding/indexing
  -> dense + BM25
  -> RRF
  -> codebase-profile results
  -> grounded answer when included by protocol
```

The measured run must use the current `codebase` profile as shipped. It must not enable the document reranker merely to improve benchmark scores.

### Primary metrics

Use the benchmark's source-grounded repository evidence to measure retrieval success. Report Recall@K/MRR-style metrics when the released labels support them. Also report exact benchmark answer scoring where the benchmark provides an authoritative scorer.

### Diagnostic metrics

- indexing time
- chunk count
- embedding tokens
- index size
- dense/BM25/RRF contribution where observable
- query latency
- retrieval misses by repository/question class

## Shared Observability

The experiment harness should emit a structured JSONL trace for each query and major stage. Keep this outside the production protocol channel.

Minimum trace fields:

- benchmark revision and run ID
- profile and dataset/query ID
- repository/file identity without leaking private content
- effective settings and model/provider identities
- selected reader/OCR route where applicable
- chunk counts
- retrieved source/chunk IDs and scores
- reranker input/output ranking where applicable
- stage durations
- embedding/request token counts where available
- answer-stage model identity
- error/degraded status

This local schema should be simple enough to map to OpenTelemetry later when OMRG moves to cloud deployment. Experiment 34 does not require an OpenTelemetry dependency.

## RAGAS

RAGAS is a secondary evaluation layer, not the primary retrieval metric.

Where the benchmark supports answer/reference evaluation, the harness may report selected RAGAS metrics such as context precision, context recall, faithfulness, and answer correctness. The exact RAGAS version, metric set, judge/provider, and model identity must be frozen before measured use.

RAGAS must be installed only in an evaluation/dev environment or optional evaluation extra. It must not become a base OMRG dependency.

If a RAGAS metric requires a paid cloud judge, the operator must approve the provider and budget before execution.

## Local Resource Gate

Before measured execution, record an agreed local envelope for:

- maximum wall time per baseline;
- maximum acceptable memory pressure;
- maximum paid-provider spend, if any.

If a smoke run shows that the frozen subset cannot complete inside that envelope, reduce the subset before freeze or stop and move the larger benchmark to a later cloud proposal. Do not silently change the subset after measured scoring starts.

## Validity Controls

- Freeze exact FinanceBench question IDs and source PDF hashes.
- Freeze exact RepoProbe repository identities, commit SHAs, and question IDs.
- Freeze effective OMRG settings and all model/provider identities.
- Freeze scoring code and metric definitions.
- Record repository SHA and dependency-lock hashes.
- Preserve failed documents, repositories, and queries in denominators.
- Do not tune on measured outcomes.
- Run 34A and 34B sequentially.

## Draft Open Questions

1. Which exact FinanceBench questions and PDFs make up the 34A subset?
2. Which two RepoProbe repositories and question IDs make up 34B?
3. Which embedding provider/model is the local reference configuration?
4. Is grounded-answer scoring mandatory for both profiles or secondary?
5. Which RAGAS metrics and judge configuration are acceptable?
6. What Mac wall-time/memory budget defines the local ceiling?
7. At what scale should the follow-up move to cloud deployment?

## Decision Rule

Experiment 34 establishes two local OMRG baselines. It does not need to prove superiority over another framework.

The report should identify quality, failure stage, latency, and resource bottlenecks. Larger benchmark runs and external framework comparisons belong in later proposals.