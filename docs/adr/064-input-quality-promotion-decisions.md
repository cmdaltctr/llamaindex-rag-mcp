# ADR-064: Input-Quality Promotion Evidence and OCR Default Decision

**Date:** 2026-09-09
**Settled:** 2026-09-10
**Status:** Accepted — the OCR routing/default decision was settled by the operator on 2026-09-10
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `improve-rag-input-quality-5`
**Related:** [ADR-062](062-isolate-paddleocr-vl-in-a-versioned-ocr-worker.md) (worker boundary, lifecycle, protocol), [ADR-063](063-model-token-aware-markdown-chunking.md) (tokenizer and chunker), [ADR-018](018-balanced-retrieval-defaults.md), [ADR-037](037-architecture-v2-conformance.md)

## Recovery correction (2026-09-09)

The earlier version incorrectly recorded the experiment 28 gate result as an
accepted operator decision. The evidence remains intact, but a machine verdict
does not approve a routing policy or an OCR default. The OCR portion of the
original change was reopened pending operator approval.

## Settled decision (2026-09-10)

The operator settled the OCR routing/default disposition on 2026-09-10:

1. `OCR_FALLBACK_ENABLED` stays `false` — OCR remains off by default.
2. Both routing thresholds stay at their `0.0` never-trigger sentinels.
3. `mixed` is removed from `OCR_UNCONDITIONAL_TYPES`; mixed PDFs now route
   by the calibrated threshold gate, not unconditionally.
4. Further OCR promotion remains deferred pending a future preregistered
   routing study on a fresh corpus.

The model-token chunking promotion, the query-instruction measurement, and all
historical reports remain recorded. The mixed-routing defect described in
the experiment 28 evidence is fixed: `mixed` is no longer in the unconditional
routing set (see `src/omrg/core/ingestion/ocr_identity.py`).

## Context

`improve-rag-input-quality-5` proposed three independent improvements to
what OMRG feeds its index:

1. Route scanned PDFs through an isolated PaddleOCR-VL worker instead of
   silently indexing nothing.
2. Chunk Markdown by real model tokens instead of a four-characters-per-
   token estimate.
3. Prefix queries with a task instruction to reshape query vectors.

Each was implemented behind a setting whose packaged default was left
unchanged, and each was to be promoted only on evidence. Task 1.6
required the promotion gates to be frozen **before any candidate was
measured**, in their own commit, with thresholds derived from the Stage 1
baselines rather than chosen.

This ADR records what the evidence said and what shipped. It does not
restate the worker's boundary, lifecycle or protocol (ADR-062) or the
chunker's design (ADR-063).

## Decision

### 1. Promoted: model-token Markdown chunking

`EMBEDDING__TOKENIZER_MODEL` and `EMBEDDING__TOKENIZER_REVISION` ship as
packaged defaults (`Qwen/Qwen3-Embedding-4B` @ `5cf2132a…`), activating
the `semantic-text-splitter` path. Design in ADR-063.

Experiment 25 passed all four frozen gates. Experiment 27 re-measured the
same arm a day later and it cleared the quality bar again (R@5 0.2365 ≥
0.231), with the published figure reproduced to +0.000314.

The benefit is cost and input-contract correctness, not retrieval
quality: embedded request tokens 0.9749× baseline, largest chunk halved
from 2,087 to 1,120 payload tokens, 22,281 chunks against 32,631.
Retrieval is a measured wash — R@5 sits 2.0 pp below baseline, inside the
±2.48 pp noise band. Mean query latency rose from 1,023 ms to 1,593 ms;
the fix if that bites is a smaller `CHUNKING__MARKDOWN_CHUNK_SIZE`, not a
return to character budgeting.

### 2. Rejected: the query instruction

`EMBEDDING__QUERY_INSTRUCTION` keeps its empty packaged default. The seam
ships and is documented as opt-in; the evaluated instruction text does
not become a default.

The candidate was
`Given a user query, retrieve passages that provide relevant and accurate
evidence for answering the query.`

Experiment 26 measured a paired R@5 lift of **−0.0246** against a frozen
requirement of **+0.0300**, with identifier-heavy R@10 at 0.2563 against
0.2583. The degradation exceeds its own paired bootstrap half-width
(±0.0155), so it is a real effect rather than noise, and nothing improved
at any cutoff. Experiment 27 reproduced the direction on a second,
differently-chunked index (−0.0128).

The instruction text was **not** rewritten and re-run against the same
gate. Tuning a candidate until it clears a gate it already failed turns
the gate into decoration. A different instruction is a new experiment
with its own frozen plan.

### 3. Settled: the OCR routing defaults (2026-09-10)

`OCR_FALLBACK_ENABLED` stays `false`. `OCR_FALLBACK_MIN_CONFIDENCE` and
`OCR_FALLBACK_PAGE_FRACTION` stay at their `0.0` never-trigger sentinels.
The calibrated `0.5` / `0.5` values are documented in `.env.example` and
in the ingestion guide as what an operator should set when enabling OCR.

The isolated worker itself remains an opt-in capability described by ADR-062.
The operator settled the OCR routing/default disposition on 2026-09-10:
OCR stays off by default, `mixed` PDFs route by the threshold gate (not
unconditionally), and further OCR promotion remains deferred.

This is the decision that changed on evidence. Experiment 24 passed all
five of its frozen gates on five held-out fixtures, which looked like
grounds for promotion. Experiment 28 then measured the same gate against
79 real documents from a working academic library and failed both of its
frozen gates:

| Gate    | Rule                                   | Measured                     |
| ------- | -------------------------------------- | ---------------------------- |
| Safety  | zero documents with a text layer route | **1**                        |
| Benefit | needs-OCR Wilson 95% lower bound > 1%  | 2/79 = 2.5%, CI [0.7%, 8.8%] |

The safety failure is one 991-page document classified `mixed` at
confidence 0.76 carrying **1,127 characters per page** — a healthy text
layer — with only **10 of 991 pages** flagged. At the time of the
experiment, `mixed` was in `OCR_UNCONDITIONAL_TYPES`, so it bypassed the
calibrated thresholds entirely, and whole-file dispatch then multiplied
the mistake by the page count: a projected **29.3 wasted OCR hours**,
turning an 80-second corpus into a **1,375× slowdown**. This defect was
fixed on 2026-09-10 (see the "Mixed-routing defect" section below).

Two findings qualify that verdict and belong in the record:

- **The calibration is the good part.** `doc_067` was classified
  `text_based` at confidence **1.0** while extracting **zero characters
  across 17 pages**. Only the 0.5 page-fraction threshold caught it;
  classification alone would have missed it. Every false route came from
  the unconditional `pdf_type` rule instead.
- **The benefit gate failed on resolution, not absence.** The Wilson
  interval runs to 8.8%. As many as one document in eleven could need
  OCR and n = 79 cannot tell. The prevalence is unresolved, not zero.

## Frozen gates and outcomes

Every threshold was committed before its measurement.

| Exp | Task | Gate                    |  Threshold |     Measured |       Verdict        |
| --- | ---- | ----------------------- | ---------: | -----------: | :------------------: |
| 24  | 5.1  | structured failures     |          0 |            0 |         PASS         |
| 24  | 5.1  | fast-path byte identity |  0 altered |            0 |         PASS         |
| 24  | 5.1  | worker s/page p95       |      ≤ 180 |        156.9 |         PASS         |
| 24  | 5.1  | routing decision p95    |    ≤ 50 ms |      2.26 ms |         PASS         |
| 25  | 5.2  | mean R@5                |    ≥ 0.231 |       0.2362 |         PASS         |
| 25  | 5.2  | identifier-heavy R@10   |   ≥ 0.2583 |       0.2775 |         PASS         |
| 25  | 5.2  | embedded-token ratio    |     ≤ 1.15 |       0.9749 |         PASS         |
| 25  | 5.2  | query p95               | ≤ 2,850 ms |     2,183 ms |         PASS         |
| 26  | 5.3  | paired R@5 lift         |  ≥ +0.0300 |  **−0.0246** |       **FAIL**       |
| 26  | 5.3  | identifier-heavy R@10   |   ≥ 0.2583 |   **0.2563** |       **FAIL**       |
| 26  | 5.3  | query p95               | ≤ 2,850 ms | **3,543 ms** | **FAIL** (see below) |
| 27  | 5.4  | mean R@5                |    ≥ 0.231 |   **0.2237** |       **FAIL**       |
| 27  | 5.4  | identifier-heavy R@10   |   ≥ 0.2583 |       0.2699 |         PASS         |
| 27  | 5.4  | query p95               | ≤ 2,850 ms | **4,790 ms** | **FAIL** (see below) |
| 28  | 5.5  | false routing count     |          0 |        **1** |       **FAIL**       |
| 28  | 5.5  | needs-OCR Wilson lower  |     > 0.01 |    **0.007** |       **FAIL**       |

**The latency gates in experiments 26 and 27 did not discriminate.** Both
are stated in absolute milliseconds against a baseline p95 of 1,984 ms
measured on 2026-09-07. On 2026-09-09 the provider was slower for
everything: experiment 26's _raw_ arm was the slowest measurement of the
whole series at 5,543 ms, and experiment 27's raw chunking arm read
3,390 ms where experiment 25 measured the identical configuration at
2,183 ms the previous day. They are recorded as failed because a frozen
rule is not edited after the fact, and they carry no evidence about
either candidate. The quality comparisons remain trustworthy: experiment
26's raw arm reproduced experiment 22's R@5 to six decimal places, and
experiment 27's to +0.000314.

## Consequences

### Positive

- Every packaged default that changed is backed by a gate frozen before
  its measurement, and every rejection is committed with its numbers.
- The OCR worker, the routing seam, the tokenizer and the query
  instruction all ship as working, documented, opt-in capabilities. An
  operator who wants any of them turns it on.
- The near-miss is on record. Experiment 24 alone would have justified
  enabling OCR by default, and doing so would have imposed a 1,375×
  slowdown on an ordinary paper library. Fixture evidence was not
  population evidence.

### Negative

- Scanned PDFs still index as empty or near-empty documents by default.
  Users with scanned material must provision the worker and enable the
  fallback themselves. Experiment 28 puts that population at 2.5% of one
  library, with an interval reaching 8.8%.
- The query-instruction seam ships with no default anyone has shown to
  help. It is a mechanism awaiting a workload that benefits.
- Task 5.4's "full candidate path" is measured in two disjoint halves.
  FreshStack has no PDFs and the PDF fixtures have no retrieval
  workload, so no single run in this change exercised all three
  components against one corpus.

### Mixed-routing defect, fixed 2026-09-10

`mixed` was in `OCR_UNCONDITIONAL_TYPES`, so a `mixed` classification
bypassed the calibrated thresholds, and task 2.4's whole-file dispatch
scaled the consequence by page count. On experiment 28's population,
removing `mixed` from that set would have produced zero false routes
while keeping both true positives.

That observation was made **after** seeing the data, **on** the data, and
is therefore exploratory. It is a hypothesis for a new preregistered
experiment on a fresh corpus, not a change made on this run's strength.
The frozen decision rule said _safety fails → promote nothing_, and it
was followed exactly. A better configuration appearing during analysis is
precisely the moment when rewriting the rule would turn the gate into
decoration.

The operator settled the disposition on 2026-09-10: `mixed` is removed
from `OCR_UNCONDITIONAL_TYPES` and now routes by the calibrated threshold
gate. The fix is in `src/omrg/core/ingestion/ocr_identity.py` and is
covered by `tests/test_ocr_routing_gate.py`. The unconditional routing
types now participate in the source index identity (schema 5) so changes
to the routing set prevent stale `skipped_unchanged` results.

## Scope limits binding on this record

- Experiment 28 sampled **one operator's curated academic library**: 79
  documents, 2,744 pages, median 3,907 characters per page, 72 of 79
  classified at confidence 1.0. It cannot license a default for scanned
  archives, historical collections, or OCR-hostile repositories it never
  saw. It establishes that on a normal modern paper library the OCR
  fallback default would have been a serious mistake, and that the
  mistake is structural rather than a matter of tuning.
- Experiments 26 and 27 measured one instruction, one embedding model
  (`qwen/qwen3-embedding-4b`), and one workload that is 200
  identifier-heavy queries out of 223. A prose-heavy corpus may behave
  differently. The three semantic queries in the set moved not at all,
  which is what n = 3 buys.
- Experiment 24's table fidelity is **unmeasured**, not passed: both
  held-out pages are prose with figures and contain no tables.

## Evidence

| Experiment                         | Verdict      | Artefacts                                                  |
| ---------------------------------- | ------------ | ---------------------------------------------------------- |
| 23 — OCR routing gate calibration  | COMPLETE     | `experiments/23-ocr-routing-gate-calibration-2026-09-07/`  |
| 24 — OCR routing evaluation        | PASS (run 2) | `experiments/24-ocr-routing-eval-2026-09-08/`              |
| 25 — Token chunking ablation       | PASS         | `experiments/25-token-chunking-ablation-2026-09-08/`       |
| 26 — Query-instruction ablation    | FAIL         | `experiments/26-query-instruction-ablation-2026-09-08/`    |
| 27 — Combined candidate path       | FAIL         | `experiments/27-combined-candidate-path-2026-09-09/`       |
| 28 — PDF classification prevalence | FAIL         | `experiments/28-pdf-classification-prevalence-2026-09-09/` |

Experiment 24 run 1 failed honestly and is preserved in the record
(commit `a7d7cd2`): the original fixtures were 605-byte blank PDFs with
nothing to OCR. The repair replaced them with rasterised CC0 pages
(commit `786055e`) and the frozen gates were never touched.
