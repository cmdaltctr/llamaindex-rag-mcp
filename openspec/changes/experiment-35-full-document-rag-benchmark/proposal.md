# Experiment 35: Local OMRS Profile Baselines

> Status: DRAFT. Run the two local baselines only after the subset identities, model identities, scoring rules, and local resource budget are frozen.

## Why

OMRS needs one full evaluation of each main profile before larger cloud benchmarks or comparisons with other frameworks.

The first baseline should stay small enough to run on the operator's Mac. The document and codebase runs should execute separately, not concurrently. This proves the evaluation harness, exposes bottlenecks, and establishes a reproducible local baseline before cloud deployment.

## What Changes

- Split Experiment 35 into two sequential local baselines:
  - **35A — Documents:** a small frozen FinanceBench subset through the current `documents` profile.
  - **35B — Codebase:** the current `codebase` profile in two parts. **35B-1** scores answers on a small frozen RepoProbe subset. **35B-2** measures retrieval on a labelled code retrieval set. RepoProbe has no retrieval labels, so it cannot give Recall@K.
- Run 35A and 35B one at a time on the Mac.
- Keep retrieval metrics as the primary quality evidence.
- Add lightweight experiment observability with structured per-stage JSONL traces.
- Record reader/OCR path, chunking, embedding, retrieval, reranking, answer generation, latency, token use, errors, and degradation where applicable.
- Add RAGAS as an optional evaluation-only layer for answer/context quality where the benchmark supports it. RAGAS goes in a separate `uv` dependency group, not in a published extra. The candidate version is 0.4.3. Freeze the version, the metric set and the judge before measured scoring.
- Keep RAGAS and observability tooling out of the base OMRS runtime dependency path.
- Stop local scale-up when the agreed Mac resource/runtime budget is exceeded. Larger runs move to a later cloud proposal.
- Keep LlamaIndex, Haystack, and other framework comparisons out of Experiment 35.
- Do not change production defaults from this experiment.

## Local Benchmark Choice

### 35A — Documents

Use a small frozen **FinanceBench** subset. The initial target is 30–50 questions across multiple source PDFs, with a mix of prose, numerical, and table-backed evidence.

FinanceBench labels evidence by document and page. A retrieved chunk is a hit when it comes from the gold document and the gold page. `evidence_page_num` is zero-indexed, so the harness converts it once and tests the conversion.

### 35B — Codebase

**Status of this split: confirmed by the user on 2026-10-23.**

RepoProbe (`Tencent-Hunyuan/RepoProbe`) gives each question a reference answer and a weighted checklist that an LLM judge scores. It gives no gold files or chunks. So 35B has two parts:

- **35B-1 — Answers.** Use a small frozen **RepoProbe** subset. The initial target is two pinned repositories with approximately 10–20 questions total. Freeze the repositories, commit SHAs and question IDs before measured execution. Score answers with the RepoProbe checklist scorer. RepoProbe was built for agents that explore a repository with tools. OMRS retrieves once and then answers. Report the result as "single-shot RAG on RepoProbe", never as a comparison with the agent results in the RepoProbe paper. The judge needs a hosted model, so this part needs a paid-provider budget. If that budget is not approved, drop 35B-1 first.
- **35B-2 — Retrieval.** Use a labelled code retrieval set for Recall@K and MRR. The candidate is FreshStack, which Experiments 9a and 22 already used. If the frozen `codebase` profile settings match the settings of an earlier FreshStack run, cite that run and do not repeat it. Otherwise run a small frozen subset only.

Other options considered: answers only (35B-1 alone, with no retrieval metric), or remove 35B from Experiment 35.

### Dataset licences (checked at source on 2026-10-23)

| Dataset | Licence | Source checked | Effect on this experiment |
|---|---|---|---|
| FinanceBench (open-source sample, 150 questions) | CC BY-NC 4.0 | Hugging Face dataset tag `PatronusAI/financebench`. The GitHub repository `patronus-ai/financebench` has no licence file. | Non-commercial use only. Use it for research evaluation. Do not commit the data or PDFs to this repository; keep them under the gitignored experiment folder or `DATA/`. |
| RepoProbe questions and checklists | CC BY 4.0 (data); Apache-2.0 (code) | `dataset/LICENSE` and the README of `Tencent-Hunyuan/RepoProbe` | Reuse allowed with attribution. The 50 upstream repositories keep their own licences and are not redistributed. |
| FreshStack corpus and queries (Oct 2024) | CC BY-SA 4.0 | Hugging Face card data of `freshstack/corpus-oct-2024` and `freshstack/queries-oct-2024` | Reuse allowed with attribution. Any redistributed derivative uses the same licence. |

Task 1.3 records the exact revisions and hashes and rechecks these licences at freeze.

The subset sizes may be reduced during protocol freeze if the Mac resource budget requires it. They must not be changed after measured scoring starts.

## Capabilities

### New Capabilities

- `document-rag-evaluation`: defines the local FinanceBench document-profile evaluation contract.
- `codebase-rag-evaluation`: defines the local codebase-profile evaluation contract: RepoProbe answers (35B-1) and labelled code retrieval (35B-2).
- `evaluation-observability`: defines shared benchmark tracing, RAGAS isolation, and reproducibility requirements.

### Modified Capabilities

- None.

## Impact

- Experiment/evaluation artefacts only.
- No production API or packaged default changes.
- Optional evaluation dependencies must remain outside the base install.
- The local baselines become the reference point for the later cloud-scale benchmark and later framework comparisons.