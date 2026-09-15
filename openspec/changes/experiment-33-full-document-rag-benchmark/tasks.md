# Tasks: Experiment 33 Local OMRG Profile Baselines

> DRAFT: measured execution must not begin until section 1 is complete.

## 1. Freeze the local protocol

- [ ] 1.1 Select and freeze 30–50 FinanceBench questions across multiple source PDFs for 33A.
- [ ] 1.2 Select and freeze two RepoProbe repositories, commit SHAs, and approximately 10–20 questions for 33B.
- [ ] 1.3 Record exact dataset versions, licences, download procedures, and source hashes.
- [ ] 1.4 Select the reference embedding provider/model and freeze all OMRG profile settings.
- [ ] 1.5 Decide whether grounded-answer scoring is mandatory or secondary for each profile.
- [ ] 1.6 Select the RAGAS version, metrics, and judge/provider configuration if RAGAS is used.
- [ ] 1.7 Define the Mac wall-time, memory-pressure, and paid-provider budget.
- [ ] 1.8 Remove DRAFT status only after these decisions are recorded.

## 2. Build shared evaluation observability

- [ ] 2.1 Define a secret-free JSONL trace schema for run, profile, dataset/query identity, stage timing, model identity, routing, retrieval, reranking, answer status, tokens, and failures.
- [ ] 2.2 Keep trace output outside MCP stdout and production protocol channels.
- [ ] 2.3 Record OMRG SHA, dependency-lock hashes, effective settings, index identity, and model/provider identities.
- [ ] 2.4 Design the schema so later cloud work can map it to OpenTelemetry without requiring OpenTelemetry for the Mac baseline.
- [ ] 2.5 Add RAGAS only to an evaluation/dev environment or optional evaluation extra; do not add it to the base install.

## 3. Build 33A — FinanceBench documents baseline

- [ ] 3.1 Add the Experiment 33 harness using repository experiment templates.
- [ ] 3.2 Ingest the frozen FinanceBench source PDFs through the current `documents` profile.
- [ ] 3.3 Capture parser/OCR evidence recovery, chunk preservation, retrieval, reranking, and answer-stage traces.
- [ ] 3.4 Measure Evidence Recall@1/@3/@5/@10, MRR@10, nDCG@10 where valid, and no-hit rate.
- [ ] 3.5 Measure ingestion time, OCR work, embedding tokens, chunk count, index size, and query latency.
- [ ] 3.6 Run selected RAGAS metrics only if the frozen protocol enables them.
- [ ] 3.7 Preserve failed documents and queries in denominators.

## 4. Run and report 33A

- [ ] 4.1 Run a small development smoke subset first.
- [ ] 4.2 Confirm the frozen measured subset fits the approved Mac resource envelope.
- [ ] 4.3 Run the measured 33A baseline without changing settings.
- [ ] 4.4 Publish retrieval, answer, observability, and resource results with limitations.

## 5. Build 33B — RepoProbe codebase baseline

- [ ] 5.1 Start 33B only after 33A completes or stops.
- [ ] 5.2 Ingest each frozen repository at its pinned commit through the current `codebase` profile.
- [ ] 5.3 Capture dense, sparse/BM25, RRF, retrieval-result, and answer-stage traces where available.
- [ ] 5.4 Measure benchmark-supported retrieval and answer metrics without enabling document-profile reranking.
- [ ] 5.5 Measure indexing time, embedding tokens, chunk count, index size, and query latency.
- [ ] 5.6 Run selected RAGAS metrics only if the frozen protocol enables them and they are meaningful for the benchmark.
- [ ] 5.7 Preserve failed repositories and queries in denominators.

## 6. Run and report 33B

- [ ] 6.1 Run a small development smoke subset first.
- [ ] 6.2 Confirm the frozen measured subset fits the approved Mac resource envelope.
- [ ] 6.3 Run the measured 33B baseline without changing settings.
- [ ] 6.4 Publish retrieval, answer, observability, and resource results with limitations.

## 7. Decide the next scale step

- [ ] 7.1 Compare 33A and 33B resource envelopes with the desired larger benchmark size.
- [ ] 7.2 If larger execution is not practical on the Mac, create the cloud-deployment/scale proposal rather than enlarging Experiment 33 locally.
- [ ] 7.3 Keep LlamaIndex/Haystack comparison work in a later separate proposal.
- [ ] 7.4 Use separate proposals for any production setting change suggested by Experiment 33.