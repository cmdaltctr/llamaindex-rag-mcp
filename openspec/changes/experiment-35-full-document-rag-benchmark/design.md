# Design: Experiment 35 Local OMRS Profile Baselines

## Status

DRAFT. Measured execution must not begin until both local subsets and the evaluation protocol are frozen.

## Context

OMRS has strong component-level evidence but needs a complete baseline for each primary profile. A large benchmark is premature while the evaluation harness, observability, answer scoring, and cloud deployment path are still being established.

Experiment 35 therefore starts with two small local benchmarks that run sequentially on the operator's Mac.

## Goals

- Evaluate the current `documents` profile end to end on a small real document benchmark.
- Evaluate the current `codebase` profile on answer quality (RepoProbe) and on retrieval (a labelled code retrieval set).
- Capture stage-level observability so failures can be attributed to the correct pipeline stage.
- Add optional RAGAS evaluation without coupling RAGAS to production OMRS.
- Establish a reproducible local baseline before cloud scale-up.

## Non-Goals

- Do not compare against historical OMRS.
- Do not compare against LlamaIndex, Haystack, LangChain, or other frameworks.
- Do not run a large benchmark locally.
- Do not tune production defaults on the measured subsets.
- Do not add RAGAS, OpenTelemetry, or other evaluation tooling to the base runtime dependency path.

## Execution Order

Run the two baselines separately:

```text
35A FinanceBench / documents
        ↓ complete + report
35B-1 RepoProbe answers / codebase
35B-2 labelled code retrieval / codebase
        ↓ complete + report
cloud-scale benchmark later
```

The two measured runs must not execute concurrently on the Mac.

## 35A — Document Profile

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

A retrieved chunk is a hit when its source is the gold `evidence_doc_name` and its page is the gold page. FinanceBench `evidence_page_num` is zero-indexed. The harness converts it to the page numbering that OMRS stores in exactly one function, with a unit test on a known page. A chunk that spans pages is a hit when any of its pages is the gold page. A question with several evidence entries is a hit at K when any gold page is hit within the top K.
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

## 35B — Codebase Profile

### Status

The user confirmed the split into 35B-1 and 35B-2 on 2026-10-23.

### Why two parts

RepoProbe gives each question a reference answer and a weighted checklist. An LLM judge scores the checklist. RepoProbe gives no gold files or chunks, so it cannot give Recall@K or MRR. Retrieval needs a second, labelled set.

### 35B-1 corpus: RepoProbe answers

Use a frozen RepoProbe subset. Initial target: two pinned repositories and approximately 10–20 questions total. Take each commit SHA from `repos_info.json` and check that the checkout matches it. The RepoProbe history records an earlier fetch script that cloned the branch tip instead of the snapshot commit.

Score answers with the RepoProbe checklist scorer. Some checklist items ask for facts that are not in the source code, for example a commit hash. Report the share of such items. RepoProbe evaluates agents that explore a repository with tools. OMRS retrieves once and then answers. Label the result "single-shot RAG on RepoProbe" and do not compare it with the agent scores in the RepoProbe paper.

The checklist judge needs a hosted model. If the paid-provider budget in task 1.7 does not cover it, drop 35B-1 and keep 35B-2.

#### 35B-1 scoring (decided 2026-10-23)

- Call RepoProbe's `SimpleScorer.score_answer_multiple(question, ModelAnswer(...), num_iterations, repo_info)` directly, at a pinned RepoProbe commit. Do not use `evaluator.py`. Its Docker agent container is not needed: the scorer takes a plain answer string (checked in `scorer.py` on 2026-10-23).
- Judge: `glm-5.3` through the Z.AI API, with `reasoning_effort: low`. GLM-5.3 cannot turn thinking off (Z.AI docs: `thinking.type=disabled` returns an error), and its default effort is `max`. So the frozen config sets `low` explicitly. Pass `scoring_model="glm-5.3"`, because the scorer defaults to `gpt-5.2`. Point `OPENAI_SCORING_BASE_URL` and `OPENAI_SCORING_API_KEY` at the Z.AI OpenAI-compatible endpoint.
- `num_iterations=3`. Report the mean and the spread across the three judge calls per question.
- Optional judge check: score 5 frozen questions again with GPT-5.6 Sol at `reasoning.effort: low` through OpenRouter. Report how often the two judges agree within 1 point out of 10. The check informs the limitations section only; it does not replace the GLM-5.3 score. Confirm the OpenRouter model slug at freeze.
- Before freeze, read `agent_configs/model_client.py` (how it passes `reasoning_effort` and `thinking` to the scoring endpoint) and `prompt_templates_en.py` (what `repo_info` adds to the judge prompt). If the client cannot send `reasoning_effort: low`, record the effort the judge actually used.
- Neither judge is the RepoProbe paper's `gpt-5.2`, so 35B-1 scores are not comparable with the paper's tables. The report says so.

### 35B-2 corpus: labelled code retrieval (decided 2026-10-23)

Use the FreshStack LangChain slice exported by `prepare_freshstack.py` with seed 20260530: about 10,024 parent documents and all 223 queries, with the qrels of Experiments 9a and 22. Use all 223 queries. Indexing is the main cost; queries are cheap, and a smaller set only widens the error bars.

Experiment 22 does not count as the 35B-2 baseline. It used standard OMRS ingestion with default chunking (32,631 chunks), `qwen/qwen3-embedding-4b` through OpenRouter, hybrid retrieval with RRF k=60, rerank off and top_k 50. The `codebase` profile sets top_k 20, the `code` chunking fallback, a wider extension list and file-type taxonomy. So 35B-2 builds a new index through the frozen `codebase` profile. Experiment 22 is a reference point: report it beside 35B-2 and name the settings that differ. (Experiment 22's protocol says "one vector per parent doc"; its results file records chunked ingestion. The results file is the record. Experiment 9a used one vector per parent document, so 9a numbers are not comparable.)

Map each retrieved chunk to its parent document and keep only the first rank of each parent before scoring, as Experiment 22's `run_eval.py` does. Reuse that mapping code.

Cells:

1. Reference cell: the frozen reference embedding model from task 1.4. This is the 35B-2 baseline.
2. Comparison cell: local `qwen3-embedding:0.6b` through the same `codebase` profile, if the reference model is not 0.6B. It shows what the smaller local model costs in retrieval quality. It is secondary and never replaces the baseline.

### Embedding model choice (task 1.4)

Decide after timing, not before. On the Mac that will run the measured runs, embed one fixed slice of 200 FreshStack documents with each candidate: local Qwen3-Embedding-4B, OpenRouter `qwen/qwen3-embedding-4b`, and local `qwen3-embedding:0.6b`. Record wall time, tokens and peak memory. Extrapolate each to the full corpus. Then freeze one reference model for both 35A and 35B, with the reason. The timing slice is a planning measurement, not a scored run. Record the hardware (chip, memory, GPU cores) in the manifest of every run, because timings from the current machine (M5 Pro, 48 GB, 16-core GPU) do not transfer.

Measurement machine, expected the week of 2026-10-26: MacBook Pro with Apple M5 Pro (18-core CPU, 20-core GPU, 16-core Neural Engine), 64 GB unified memory, 1 TB SSD. Run the timing slice and every measured 35A and 35B run on this machine. Do not run task 1.4 on the current machine.

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

- 35B-1: RepoProbe checklist score (overall, knowledge and clarity) and perfect-solve rate, from the RepoProbe scorer with a frozen judge.
- 35B-2: Recall@1/@3/@5/@10 and MRR@10 against the labelled set's gold documents.

Do not report retrieval metrics for 35B-1.

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

This local schema should be simple enough to map to OpenTelemetry later when OMRS moves to cloud deployment. Experiment 35 does not require an OpenTelemetry dependency.

## RAGAS

RAGAS is a secondary evaluation layer, not the primary retrieval metric.

Where the benchmark supports answer/reference evaluation, the harness may report selected RAGAS metrics such as context precision, context recall, faithfulness, and answer correctness. The exact RAGAS version, metric set, judge/provider, and model identity must be frozen before measured use.

RAGAS goes in a separate `uv` dependency group (for example `eval`), not in a published extra, so users never install it. The candidate version is 0.4.3 (Apache-2.0, Python 3.9 or later). It pulls in `langchain`, `datasets` and `tiktoken`. Before adding it, run a dry resolve and check whether `tests/test_dependency_floors.py` needs an exemption. It must not become a base OMRS dependency.

RAGAS accepts any OpenAI-compatible endpoint as its judge, including a local server. A small local judge can give noisy scores on multi-step metrics such as faithfulness. Freeze the judge choice with its cost in task 1.6.

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
- Freeze the 35B-2 dataset revision, question IDs and gold labels.
- Freeze the FinanceBench page-index conversion and its test.
- Freeze effective OMRS settings and all model/provider identities.
- Freeze scoring code and metric definitions.
- Record repository SHA and dependency-lock hashes.
- Preserve failed documents, repositories, and queries in denominators.
- Do not tune on measured outcomes.
- Run 35A and 35B sequentially.

## Draft Open Questions

1. Which exact FinanceBench questions and PDFs make up the 35A subset?
2. Which two RepoProbe repositories and question IDs make up 35B-1?
3. Which embedding provider/model is the local reference configuration? Decided by the timing slice in task 1.4.

Resolved on 2026-10-23: 35B-2 uses the full FreshStack LangChain slice with a new `codebase`-profile index, and Experiment 22 is a reference only. The RepoProbe scorer accepts plain answers without its agent container; the judge is GLM-5.3 at `reasoning_effort: low`.
4. Is grounded-answer scoring mandatory for both profiles or secondary?
5. Which RAGAS metrics and judge configuration are acceptable?
6. What Mac wall-time/memory budget defines the local ceiling?
7. At what scale should the follow-up move to cloud deployment?

## Decision Rule

Experiment 35 establishes two local OMRS baselines. It does not need to prove superiority over another framework.

The report should identify quality, failure stage, latency, and resource bottlenecks. Larger benchmark runs and external framework comparisons belong in later proposals.