# Experiment 34: Local OMRG Profile Baselines

> Status: DRAFT. Run the two local baselines only after the subset identities, model identities, scoring rules, and local resource budget are frozen.

## Why

OMRG needs one full evaluation of each main profile before larger cloud benchmarks or comparisons with other frameworks.

The first baseline should stay small enough to run on the operator's Mac. The document and codebase runs should execute separately, not concurrently. This proves the evaluation harness, exposes bottlenecks, and establishes a reproducible local baseline before cloud deployment.

## What Changes

- Split Experiment 34 into two sequential local baselines:
  - **34A — Documents:** a small frozen FinanceBench subset through the current `documents` profile.
  - **34B — Codebase:** a small frozen RepoProbe subset through the current `codebase` profile.
- Run 34A and 34B one at a time on the Mac.
- Keep retrieval metrics as the primary quality evidence.
- Add lightweight experiment observability with structured per-stage JSONL traces.
- Record reader/OCR path, chunking, embedding, retrieval, reranking, answer generation, latency, token use, errors, and degradation where applicable.
- Add RAGAS as an optional evaluation-only layer for answer/context quality where the benchmark supports it.
- Keep RAGAS and observability tooling out of the base OMRG runtime dependency path.
- Stop local scale-up when the agreed Mac resource/runtime budget is exceeded. Larger runs move to a later cloud proposal.
- Keep LlamaIndex, Haystack, and other framework comparisons out of Experiment 34.
- Do not change production defaults from this experiment.

## Local Benchmark Choice

### 34A — Documents

Use a small frozen **FinanceBench** subset. The initial target is 30–50 questions across multiple source PDFs, with a mix of prose, numerical, and table-backed evidence.

### 34B — Codebase

Use a small frozen **RepoProbe** subset. The initial target is two pinned repositories with approximately 10–20 questions total. Exact repositories and question IDs must be frozen before measured execution.

The subset sizes may be reduced during protocol freeze if the Mac resource budget requires it. They must not be changed after measured scoring starts.

## Capabilities

### New Capabilities

- `document-rag-evaluation`: defines the local FinanceBench document-profile evaluation contract.
- `codebase-rag-evaluation`: defines the local RepoProbe codebase-profile evaluation contract.
- `evaluation-observability`: defines shared benchmark tracing, RAGAS isolation, and reproducibility requirements.

### Modified Capabilities

- None.

## Impact

- Experiment/evaluation artefacts only.
- No production API or packaged default changes.
- Optional evaluation dependencies must remain outside the base install.
- The local baselines become the reference point for the later cloud-scale benchmark and later framework comparisons.