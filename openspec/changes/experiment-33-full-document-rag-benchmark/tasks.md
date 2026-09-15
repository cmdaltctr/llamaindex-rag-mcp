# Tasks: Experiment 33 Full OMRG Document RAG Benchmark

> DRAFT: tasks after section 1 must not begin as measured benchmark work until the protocol is approved.

## 1. Resolve the draft protocol

- [ ] 1.1 Select the first-run corpus from MMLongBench-Doc-V2, FinanceBench, QASPER PDF subset, and OMRG pathology candidates.
- [ ] 1.2 Define exact dataset versions, licences, download procedures, inclusion rules, and file hashes.
- [ ] 1.3 Select the reference embedding provider/model and freeze all current OMRG settings.
- [ ] 1.4 Decide whether grounded-answer scoring is mandatory or secondary.
- [ ] 1.5 Define answer-scoring method if answer synthesis is included.
- [ ] 1.6 Define practical gates or explicitly state that the first run is descriptive baseline measurement only.
- [ ] 1.7 Approve runtime and any paid-provider budget.
- [ ] 1.8 Remove DRAFT status only after the above decisions are recorded.

## 2. Freeze benchmark identity

- [ ] 2.1 Freeze corpus, query set, qrels/gold answers, and query order.
- [ ] 2.2 Freeze scoring code and metric definitions.
- [ ] 2.3 Record repository SHA, dependency-lock hashes, effective settings, tokenizer identity, embedding identity, reranker identity, OCR worker fingerprint, and vector-store identity.
- [ ] 2.4 Define development and measured test partitions with no tuning on the measured partition.

## 3. Build the experiment harness

- [ ] 3.1 Add `experiments/33-full-document-rag-benchmark-<date>/` using repository templates.
- [ ] 3.2 Drive raw source PDFs through the current OMRG `documents` profile.
- [ ] 3.3 Capture stage outputs needed for evidence-recovery, chunk-coverage, retrieval, reranking, and optional answer scoring.
- [ ] 3.4 Emit secret-free runtime manifests and deterministic benchmark identities.
- [ ] 3.5 Preserve failed documents and queries instead of dropping them from denominators.

## 4. Validate before the measured run

- [ ] 4.1 Run preflight checks for corpus hashes, settings, models, worker provisioning, and scoring inputs.
- [ ] 4.2 Run a development smoke subset without using measured test outcomes for tuning.
- [ ] 4.3 Confirm private/local pathology data is not leaked into public artefacts.

## 5. Execute the measured baseline

- [ ] 5.1 Run the frozen benchmark without changing production settings.
- [ ] 5.2 Measure parser evidence recoverability and chunk coverage.
- [ ] 5.3 Measure Recall@1/@3/@5/@10, MRR@10, nDCG@10 where valid, and no-hit rate.
- [ ] 5.4 Measure answer correctness and grounding if the approved protocol includes Layer 4.
- [ ] 5.5 Record ingestion time, OCR work, embedding tokens, chunk count, index size, and query latency.

## 6. Report the OMRG baseline

- [ ] 6.1 Publish aggregate and per-dataset results with confidence intervals where justified.
- [ ] 6.2 Report failures by pipeline stage and preserve negative findings.
- [ ] 6.3 State limitations and benchmark coverage clearly.
- [ ] 6.4 Do not claim superiority over another framework from Experiment 33.
- [ ] 6.5 Use a separate proposal for any production change or future LlamaIndex/Haystack comparison.
