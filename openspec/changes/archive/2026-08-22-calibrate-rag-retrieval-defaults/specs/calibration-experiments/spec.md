## ADDED Requirements

### Requirement: Experiment 10b — Corrected reranker pool-size sweep

The system SHALL run a corrected reranker pool-size sensitivity experiment on
the FreshStack LangChain corpus (10,025 parents) that varies the effective
candidate pool size (`fetch_k`) across genuinely distinct values {50, 100, 200,
500} by overriding the `max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)`
formula directly.

#### Scenario: Pool sizes are genuinely distinct

- **WHEN** the evaluation runner processes the pool-size sweep cells
- **THEN** each cell MUST produce a different effective `fetch_k` value (50, 100,
  200, 500) as verified by a runtime assertion in `run_eval.py`
- **AND** the assertion MUST fail loudly if any two cells resolve to the same
  `fetch_k`

#### Scenario: Post-ADR-021 config baseline

- **WHEN** the experiment is configured
- **THEN** the baseline config MUST use `RERANK_FETCH_MULTIPLIER=3` and
  `RERANK_MAX_FETCH=100` (post-ADR-021 values)
- **AND** per-cell overrides MUST set `fetch_k` directly via the `fetch_k=`
  parameter on `search()` (per TDR-005), not by changing `RERANK_MAX_FETCH`
  alone

#### Scenario: Reranker-off reference cell

- **WHEN** the experiment includes a reranker-off cell
- **THEN** it MUST serve as the quality ceiling reference against which all
  reranker-on cells are compared

#### Scenario: Pool-size pass gate

- **WHEN** results are summarised
- **THEN** the experiment MUST report whether any pool size recovers at least
  3pp Coverage@20 over the `fetch_k=500` cell (the only cell comparable to
  Exp 10's effective pool)
- **AND** MUST report whether reranker-off still outperforms all reranker-on
  cells

---

### Requirement: Experiment 10.1 — DOC_SIMILARITY_THRESHOLD calibration

The system SHALL run a `DOC_SIMILARITY_THRESHOLD` calibration experiment that
sweeps the document-graph similarity threshold across {0.70, 0.75, 0.80, 0.85,
0.90} on a representative mixed code-plus-docs corpus, measuring cluster
coherence, cross-link false-positive rate, and community detection quality.

#### Scenario: Mixed corpus construction

- **WHEN** the experiment corpus is prepared
- **THEN** it MUST contain both code files (Python, TypeScript, Markdown) and
  prose documentation files
- **AND** the corpus MUST be large enough to produce a non-trivial document
  graph (≥ 50 documents with pairwise similarity above 0.70)

#### Scenario: Threshold sweep metrics

- **WHEN** the sweep is run
- **THEN** each threshold value MUST produce: edge count, cluster count, mean
  cluster size, modularity score, and a manual false-positive sample (10 random
  edges rated as "meaningful link" or "noise")

#### Scenario: Calibration recommendation

- **WHEN** results are summarised
- **THEN** the experiment MUST identify the threshold that maximises modularity
  while keeping the false-positive rate below 20%
- **AND** MUST report whether the current default (0.85) is within the
  acceptable range

---

### Requirement: Experiment 12 — Hybrid default promotion test (post-ADR-019)

The system SHALL run a hybrid retrieval default-promotion test that compares
`{dense, hybrid_bm25} × {rerank-off}` on the FreshStack LangChain corpus,
testing whether hybrid retrieval should be promoted to the default now that
ADR-019 disables the reranker by default.

#### Scenario: Reranker-off only

- **WHEN** the cell matrix is designed
- **THEN** it MUST contain exactly four cells: dense-off, hybrid-off,
  dense-rerank-on (reference), hybrid-rerank-on (reference)
- **AND** the promotion decision MUST be based on reranker-off cells only
- **AND** rerank-on reference cells MUST use post-ADR-021 config
  (`RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100`), giving
  `fetch_k=150` at `top_k=50` — not the original Exp 9a `fetch_k=500`

#### Scenario: Revised quality gate

- **WHEN** the promotion gate is evaluated
- **THEN** hybrid Coverage@20 MUST exceed dense Coverage@20 by at least 3
  percentage points (not the original 5pp)
- **AND** semantic query Coverage@20 MUST NOT regress by more than 2pp

#### Scenario: Statistical confidence

- **WHEN** results show a positive Coverage@20 lift
- **THEN** the experiment MUST report bootstrap 95% confidence intervals on the
  lift
- **AND** promotion MUST NOT be recommended if the CI includes zero

---

### Requirement: Experiment 9a-rerun — Post-ADR-021 reranker validation

The system SHALL re-run the four-cell grid (`{dense, hybrid} × {rerank-on,
rerank-off}`) from Experiment 9a on the FreshStack LangChain corpus using the
post-ADR-021 reranker configuration, to determine whether ADR-019's
reranker-off decision still holds when the reranker sees 150 candidates instead
of 500.

#### Scenario: Post-ADR-021 config applied

- **WHEN** the experiment is configured
- **THEN** reranker-on cells MUST use `RERANK_FETCH_MULTIPLIER=3` and
  `RERANK_MAX_FETCH=100` (post-ADR-021)
- **AND** at `top_k=50`, the effective `fetch_k` MUST be 150 (not 500 as in the
  original Exp 9a)

#### Scenario: ADR-019 validation

- **WHEN** results are compared to the original Exp 9a
- **THEN** the experiment MUST report whether reranker-on cells at `fetch_k=150`
  still degrade Coverage@20 relative to reranker-off
- **AND** MUST conclude whether ADR-019's decision is validated, invalidated, or
  uncertain

#### Scenario: Latency comparison

- **WHEN** latency metrics are recorded
- **THEN** the experiment MUST report P95 latency for each cell
- **AND** MUST compare to the original Exp 9a P95 values to verify the ADR-021
  10× speedup holds at the experiment scale

---

### Requirement: Experiment 13 — HARD_TECHNICAL_THRESHOLD calibration

The system SHALL run a `HARD_TECHNICAL_THRESHOLD` calibration experiment that
sweeps the threshold across {0.1, 0.2, 0.3, 0.5, 0.7} on a mixed
technical-plus-semantic corpus, measuring retrieval quality on both query
types to find the threshold that preserves semantic reranker benefit without
triggering on technical queries.

#### Scenario: Mixed-corpus query fractions

- **WHEN** the evaluation corpus is constructed
- **THEN** it MUST combine FreshStack LangChain (technical) and Qasper
  (semantic) queries
- **AND** MUST sweep the technical-query fraction across {100%, 90%, 75%, 50%,
  25%, 0%}
- **AND** each cell MUST contain at least 30 queries to ensure statistical
  validity (subsample larger corpora if needed; flag cells below this threshold
  in results)

#### Scenario: Per-threshold quality measurement

- **WHEN** each threshold value is evaluated
- **THEN** the experiment MUST report Coverage@20 separately for technical and
  semantic queries
- **AND** MUST identify the threshold where semantic reranker benefit is
  preserved (≥ +1pp Coverage@20 on semantic queries) while technical regression
  is minimised (≤ −1pp Coverage@20 on technical queries)

#### Scenario: Calibration recommendation

- **WHEN** results are summarised
- **THEN** the experiment MUST recommend a calibrated threshold value
- **AND** MUST report whether the current default (0.3) is within the acceptable
  range

---

### Requirement: Experiment 14 — LiteParse promotion on harder corpus

The system SHALL re-run the LiteParse PDF quality experiment on the Qasper
corpus (academic two-column PDFs) where corpus saturation is unlikely, completing
the unfilled TODO sections from Experiment 11 and validating H3 (reranker
benefit) and H2 (speed) under post-ADR-021 optimisations.

#### Scenario: Harder corpus selection

- **WHEN** the experiment corpus is chosen
- **THEN** it MUST use Qasper PDFs (academic papers, two-column layout)
- **AND** the dense-only baseline MUST NOT achieve 100% Hit@5 (corpus must have
  headroom)
- **AND** the corpus MUST contain at least 100 queries across ≥ 30 PDFs to
  ensure the promotion gate is statistically meaningful (Exp 6b/7a's
  20-paper / 80-query fixtures are insufficient for a default-flip decision)

#### Scenario: H3 validation — reranker benefit vs LiteParse

- **WHEN** reranker-on cells are compared between LiteParse and pypdf
- **THEN** the experiment MUST report whether reranking helps LiteParse more
  than pypdf (the original H3 that was inconclusive due to saturation)

#### Scenario: Exp 11 completion

- **WHEN** the results are documented
- **THEN** the experiment MUST produce a complete `results.md` with executive
  summary, per-category breakdown, and conclusion
- **AND** MUST cross-reference and supersede the unfilled Exp 11 TODO sections

#### Scenario: Post-ADR-021 latency

- **WHEN** reranker-on latency is measured
- **THEN** P95 latency MUST be recorded and compared to Exp 11's pre-ADR-021
  values (~55s for pypdf+rerank, ~30s for liteparse+rerank)
- **AND** MUST verify the ADR-021 10× speedup at the PDF experiment scale

---

### Requirement: Experiment protocol completeness

Every experiment in this batch SHALL have a complete `protocol.md` written
before any evaluation cells are run, following the experiment skill's protocol
template structure.

#### Scenario: Pre-written success criteria

- **WHEN** an experiment protocol is created
- **THEN** it MUST include success criteria / pass gates written before running
- **AND** MUST include interpretation rules that pre-commit to what each outcome
  means

#### Scenario: Checkpoint and resume support

- **WHEN** an experiment runner is written
- **THEN** it MUST save an atomic checkpoint after each completed cell
- **AND** MUST support `--resume` to skip completed cells on re-run

#### Scenario: Results documentation

- **WHEN** an experiment completes
- **THEN** its `results.md` MUST include executive summary, metrics tables, pass
  gate evaluation, and a recommendation that maps to a specific code or config
  decision
