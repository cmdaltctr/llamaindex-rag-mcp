## 1. Rename Experiment Directories

- [x] 1.1 Rename `experiments/experiment-1` → `experiments/reranker-threshold-calibration-2026-05-12` using `git mv`
- [x] 1.2 Rename `experiments/experiment-2` → `experiments/embedding-model-comparison-2026-05-19` using `git mv`
- [x] 1.3 Rename `experiments/experiment-3` → `experiments/e2e-smoke-test-metadata-2026-05-20` using `git mv`

## 2. Restructure Experiment 1 (Reranker Threshold Calibration)

- [x] 2.1 Create `protocol.md` in `reranker-threshold-calibration-2026-05-12/` with the following sections from `experiments.md`: Hypothesis/Purpose, Background, Variables (new), Environment & Prerequisites, Corpus, Method (How to Reproduce), Success Criteria, Artefacts
- [x] 2.2 Add the Variables table to `protocol.md` — Independent: similarity threshold scaling factor; Dependent: source accuracy, answer accuracy; Controlled: embedding model (nomic-embed-text), corpus (5 fixture docs), chunk size
- [x] 2.3 Add Operator field to `protocol.md` — value: `Dr Muhammad Aizat Bin Md Hawari`
- [x] 2.4 Add Status field to `protocol.md` — value: `PASS`
- [x] 2.5 Add Artefacts section to `protocol.md` listing: `protocol.md`, `results.md`, `run_experiments.py`, `experiment_results.json`
- [x] 2.6 Create `results.md` in `reranker-threshold-calibration-2026-05-12/` with: Operator, Status, Results Summary table, Key Findings, Practical Recommendations, Raw Data reference — all content taken verbatim from `experiments.md`
- [x] 2.7 Delete `experiments.md` from `reranker-threshold-calibration-2026-05-12/`

## 3. Update Experiment 2 (Embedding Model Comparison)

- [x] 3.1 Add Operator field to `protocol.md` — value: `Dr Muhammad Aizat Bin Md Hawari`
- [x] 3.2 Add Status field to `protocol.md` — value: `PASS`
- [x] 3.3 Add Variables table to `protocol.md` — Independent: embedding model; Dependent: Hit@1, Hit@3, Hit@5, MRR, avg query latency; Controlled: reranker (disabled), corpus (6 docs, 207 chunks), chunk size (512), chunk overlap (64)
- [x] 3.4 Add Artefacts section to `protocol.md` listing: `protocol.md`, `results.md`, `run_eval.py`, `eval_results.json`, `ground-truth.json`, `questions.md`, `corpus/`

## 4. Update Experiment 3 (E2E Smoke Test)

- [x] 4.1 Add Variables table to `protocol.md` — Independent: metadata extraction mode (llamaindex); Dependent: ingest error count, chunk count, metadata field presence, Hit@1 across 17 queries; Controlled: embedding model (qwen3:0.6b), reranker (enabled), corpus (6 docs), chunk size (512)
- [x] 4.2 Add Artefacts section to `protocol.md` listing: `protocol.md`, `results.md`, `questions.md`, `corpus/`

## 5. Update README Index

- [x] 5.1 Update `experiments/README.md` index table — replace `./experiment-1/`, `./experiment-2/`, `./experiment-3/` links with the new slug-date directory names
- [x] 5.2 Search the entire repo for references to `experiment-1`, `experiment-2`, `experiment-3` (check `AGENTS.md`, `openspec/`, source files) and update any stale paths to the new directory names

## 6. Verify

- [x] 6.1 Confirm all three renamed directories exist and contain `protocol.md` and `results.md`
- [x] 6.2 Confirm `experiments/README.md` index links resolve to the correct directories
- [x] 6.3 Confirm no files reference the old `experiment-1`, `experiment-2`, `experiment-3` directory names
- [x] 6.4 Confirm `experiment-1/experiments.md` no longer exists
