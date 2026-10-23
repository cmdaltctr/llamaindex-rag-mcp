# Tasks: Experiment 35 Local OMRS Profile Baselines

> DRAFT: measured execution must not begin until section 1 is complete.

## 1. Freeze the local protocol

- [ ] 1.1 Select and freeze 30–50 FinanceBench questions across multiple source PDFs for 35A.
- [ ] 1.2 Select and freeze two RepoProbe repositories, commit SHAs from `repos_info.json`, and approximately 10–20 questions for 35B-1. Select and freeze the 35B-2 labelled code retrieval set (candidate: FreshStack), its revision and question IDs, and record whether an earlier FreshStack run already matches the frozen `codebase` settings.
- [ ] 1.3 Record exact dataset versions, licences, download procedures, and source hashes. Recheck each licence against the table in the proposal (checked 2026-10-23) at the frozen revision; keep FinanceBench data out of git (CC BY-NC 4.0).
- [ ] 1.3a Record the FinanceBench page-level hit rule from design 35A (gold document and gold page, zero-indexed `evidence_page_num` converted once).
- [ ] 1.4 Select the reference embedding provider/model and freeze all OMRS profile settings.
- [ ] 1.5 Decide whether grounded-answer scoring is mandatory or secondary for each profile.
- [ ] 1.6 Select the RAGAS version (candidate 0.4.3), metrics, and judge/provider configuration if RAGAS is used.
- [ ] 1.7 Define the Mac wall-time, memory-pressure, and paid-provider budget, including the RepoProbe checklist judge for 35B-1.
- [ ] 1.8 Remove DRAFT status only after these decisions are recorded.

## 2. Build shared evaluation observability

- [ ] 2.1 Define a secret-free JSONL trace schema for run, profile, dataset/query identity, stage timing, model identity, routing, retrieval, reranking, answer status, tokens, and failures.
- [ ] 2.2 Keep trace output outside MCP stdout and production protocol channels.
- [ ] 2.3 Record OMRS SHA, dependency-lock hashes, effective settings, index identity, and model/provider identities.
- [ ] 2.4 Design the schema so later cloud work can map it to OpenTelemetry without requiring OpenTelemetry for the Mac baseline.
- [ ] 2.5 Add RAGAS only to a separate `uv` dependency group, not to a published extra or the base install. Run a dry resolve first and check `tests/test_dependency_floors.py`.

## 3. Build 35A — FinanceBench documents baseline

- [ ] 3.1 Add the Experiment 35 harness using repository experiment templates.
- [ ] 3.2 Ingest the frozen FinanceBench source PDFs through the current `documents` profile.
- [ ] 3.3 Capture parser/OCR evidence recovery, chunk preservation, retrieval, reranking, and answer-stage traces.
- [ ] 3.4 Measure Evidence Recall@1/@3/@5/@10, MRR@10, nDCG@10 where valid, and no-hit rate, using the page-level hit rule and a unit test of the page-index conversion.
- [ ] 3.5 Measure ingestion time, OCR work, embedding tokens, chunk count, index size, and query latency.
- [ ] 3.6 Run selected RAGAS metrics only if the frozen protocol enables them.
- [ ] 3.7 Preserve failed documents and queries in denominators.

## 4. Run and report 35A

- [ ] 4.1 Run a small development smoke subset first.
- [ ] 4.2 Confirm the frozen measured subset fits the approved Mac resource envelope.
- [ ] 4.3 Run the measured 35A baseline without changing settings.
- [ ] 4.4 Publish retrieval, answer, observability, and resource results with limitations.

## 5. Build 35B — codebase baseline (35B-1 RepoProbe answers, 35B-2 labelled retrieval)

- [ ] 5.1 Start 35B only after 35A completes or stops.
- [ ] 5.2 Ingest each frozen RepoProbe repository at its pinned commit through the current `codebase` profile, and check that each checkout matches its SHA.
- [ ] 5.3 Capture dense, sparse/BM25, RRF, retrieval-result, and answer-stage traces where available.
- [ ] 5.4 35B-1: score answers with the RepoProbe checklist scorer and the frozen judge, without enabling document-profile reranking. Report no retrieval metric for 35B-1.
- [ ] 5.4a 35B-2: measure Recall@1/@3/@5/@10 and MRR@10 on the frozen labelled set, or cite the earlier FreshStack run when task 1.2 recorded a settings match.
- [ ] 5.5 Measure indexing time, embedding tokens, chunk count, index size, and query latency.
- [ ] 5.6 Run selected RAGAS metrics only if the frozen protocol enables them and they are meaningful for the benchmark.
- [ ] 5.7 Preserve failed repositories and queries in denominators.

## 6. Run and report 35B

- [ ] 6.1 Run a small development smoke subset first.
- [ ] 6.2 Confirm the frozen measured subset fits the approved Mac resource envelope.
- [ ] 6.3 Run the measured 35B baseline without changing settings.
- [ ] 6.4 Publish retrieval (35B-2), answer (35B-1), observability, and resource results with limitations. Label 35B-1 "single-shot RAG on RepoProbe".

## 7. Decide the next scale step

- [ ] 7.1 Compare 35A and 35B resource envelopes with the desired larger benchmark size.
- [ ] 7.2 If larger execution is not practical on the Mac, create the cloud-deployment/scale proposal rather than enlarging Experiment 35 locally.
- [ ] 7.3 Keep LlamaIndex/Haystack comparison work in a later separate proposal.
- [ ] 7.4 Use separate proposals for any production setting change suggested by Experiment 35.