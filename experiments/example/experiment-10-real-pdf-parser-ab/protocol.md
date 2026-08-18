# Experiment 10 — Real-PDF parser A/B: pypdf vs LiteParse

**Template ID:** `example/experiment-10-real-pdf-parser-ab`  
**Status:** PLANNED  
**Role:** repaired replacement for the current invalid Markdown-based PDF experiment

## 1. Research question

On an immutable corpus of **actual PDF bytes**, how do pypdf and LiteParse affect extracted text, chunk/index contents, retrieval quality and ingestion-stage performance under otherwise identical RAG settings? As a secondary interaction, does reranking benefit one parser's output more than the other?

## 2. Pre-registered hypotheses

- **H1 — treatment validity:** every PDF is genuinely parsed by the declared parser backend; parser outputs have independent artefact identities and the runner never embeds pre-extracted dataset text in place of PDF parsing.
- **H2 — corpus headroom:** reranker-off dense baseline is not saturated (pre-register gate, e.g. Hit@5 < 100% and sufficient missed queries to estimate differences).
- **H3 — parser quality non-inferiority:** LiteParse Coverage@20 is no worse than pypdf by more than 2pp with reranking off.
- **H4 — parser quality improvement (if claimed):** any positive LiteParse-vs-pypdf primary lift must meet a pre-registered practical margin and paired CI rule; non-inferiority alone does not prove superiority.
- **H5 — parse speed:** LiteParse median total parse time per PDF is lower than pypdf, reported separately from embedding/write time.
- **H6 — reranker interaction (secondary):** `(LiteParse_on - LiteParse_off) - (pypdf_on - pypdf_off)` is reported with paired uncertainty; promotion does not depend on this interaction unless pre-registered as a decision gate.

## 3. Experimental unit

Quality unit: one query linked to relevant source PDF(s)/evidence.  
Parser performance unit: one PDF.  
Index unit: one parser-specific immutable parsed corpus/index.

Use >=30 PDFs and >=100 labelled queries as a minimum only if those counts provide adequate evidence; larger is preferable. Query/evidence labels must be defined independently of parser output.

## 4. Manipulated / independent variables

Factor A — PDF parser:
- `pypdf`
- `liteparse`

Factor B — reranker (secondary factorial):
- `off`
- `on` using one fixed backend/model/device proven by Experiment 5.

The primary parser comparison is reranker-off so parser effects are interpretable without reranker interaction.

## 5. Controlled variables

- exact PDF bytes/checksums;
- query/qrel/evidence labels;
- document set and page range;
- OCR setting fixed unless OCR itself becomes a separate experiment;
- chunker type/size/overlap;
- metadata extraction mode;
- embedding provider/model;
- vector store backend/mode;
- top_k/fetch policy;
- hybrid off for primary parser effect unless explicitly pre-registered otherwise;
- reranker backend/model/device for on cells;
- software/dependency lock and hardware for performance timing.

Parser changes create different parsed-text/index identities; every downstream setting remains fixed.

## 6. Blocking / stratification variables

Pre-label PDFs before treatment where feasible:

- single-column vs multi-column;
- table-heavy;
- equation-heavy;
- scanned/OCR-needed vs digital text (only if OCR mode supports both fairly);
- page count/size bucket.

Report parser failures and quality by strata; do not drop failed PDFs post hoc without a pre-registered missing-data rule.

## 7. Dependent variables

### Parser output/process

- parse success/failure;
- parse wall time per PDF;
- extracted characters/tokens;
- page count/page mapping coverage;
- empty/near-empty page count;
- text artefact checksum;
- optional structural heuristics (heading/table markers) if defined before run.

### Index/ingestion

- chunk count and token-size distribution;
- embedding time;
- vector-store write time;
- total ingestion time;
- peak RSS if measured.

### Retrieval quality

Primary: Coverage@20.  
Secondary: Hit@5/10, Recall@50, MRR@10, alpha-nDCG@10 where labels support it.

### Reranker interaction

- parser-specific on-off delta;
- difference-in-differences for primary metric.

## 8. Cell matrix

| Cell | Parser | Rerank | Role |
|---|---|---|---|
| P0 | pypdf | off | parser control / primary |
| L0 | LiteParse | off | parser treatment / primary |
| P1 | pypdf | on | secondary interaction |
| L1 | LiteParse | on | secondary interaction |

Only two indexes are built: one per parser. Rerank cells reuse their parser index read-only.

## 9. Corpus and ground truth

### Critical requirement

The corpus directory contains actual `.pdf` files, not Markdown generated from a dataset's already-extracted `full_text` field.

For every PDF commit/record:

- source identifier and lawful/reproducible acquisition instruction;
- SHA-256 of PDF bytes;
- size/page count when known.

Ground truth questions/qrels/evidence references must be parser-independent. If Qasper is used, source PDFs must actually be obtained and frozen/referenced; if that cannot be done reproducibly, select another real-PDF corpus rather than substituting Qasper text.

## 10. Randomisation / counterbalancing

### Parser timing

Alternate parser order per PDF (or run each parser in fresh processes with counterbalanced order) to avoid always giving one parser hotter filesystem caches. If cold-cache control is impractical, report the limitation and run multiple rotations.

### Retrieval

Every query runs against both parser indexes. Counterbalance P0/L0/P1/L1 order by query/repetition.

## 11. Repetitions and warm-up

Parser timing: >=3 fresh-process repetitions per parser/PDF subset if making strong speed claims; at minimum use enough repetitions to separate startup from steady parse time.  
Quality: one complete paired query result per cell after valid preflight.  
Reranker latency: analyse separately using repeated subset if required.

## 12. Preflight assertions

Before embedding any parser output:

- input file extension is `.pdf` and PDF checksum matches manifest;
- effective document reader equals declared parser;
- parser invocation counter/diagnostic confirms it ran for every input;
- output text artefact is written with parser identity and checksum;
- no code path loads dataset Markdown/full_text as the parser treatment input;
- parser-specific immutable index names differ;
- embed/chunk settings are identical across parser indexes;
- reranker cells reuse the correct parser index.

If parser outputs happen to be byte-identical for a simple PDF, that is allowed; the treatment is proven by invocation, not forced difference.

## 13. Abort / invalid-cell criteria

- PDF parser was not invoked;
- corpus contains pre-extracted text instead of source PDFs;
- parser-specific indexes use different embedding/chunk settings;
- qrels are generated/changed from one parser's output after seeing treatment;
- parser fallback silently substitutes another reader in a treatment cell;
- systematic parser failure causes missing documents without the pre-registered missing-data rule being applied.

## 14. Success / decision gates

- H1 is mandatory: 100% treatment-valid invocation for included PDFs or explicitly reported parser failures; no silent fallback.
- H2: corpus headroom gate passes; if saturated, quality superiority is INCONCLUSIVE even if speed can still be measured.
- H3: paired primary delta `L0 - P0 >= -2pp` with a one-sided/non-inferiority CI appropriate to the pre-registered margin.
- H4 superiority, only if claimed: pre-register a positive practical margin (e.g. +2pp/+3pp) and require paired CI support.
- H5: LiteParse parse-time median lower than pypdf, with raw per-PDF paired timings; total ingestion speed is reported separately.
- H6: report interaction with CI; no post-hoc promotion solely because one cell looks largest.

## 15. Analysis plan

1. validate parser invocation and missingness;
2. compare paired parser output statistics per PDF;
3. compare parse time paired by PDF;
4. compare chunk/index statistics;
5. run paired P0 vs L0 primary retrieval analysis with bootstrap over queries (and optionally clustered by document if queries are highly correlated within PDF);
6. calculate reranker on-off deltas and difference-in-differences;
7. report strata with sample sizes;
8. decompose total ingestion time: parse -> chunk -> embed -> write.

## 16. Threats to validity

- query labels may target information preserved in both parsers and miss layout/table differences;
- queries within one PDF are correlated, so naive query bootstrap may understate uncertainty; consider document-cluster bootstrap and pre-register it;
- parser warm/cold filesystem caches can affect timing;
- OCR changes the treatment and should be fixed or separately factored;
- embedding time can dominate end-to-end ingestion and obscure parser speed, hence stage decomposition is mandatory.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/prepare_real_pdfs.py
uv run python experiments/<promoted-dir>/parse_corpus.py --reader pypdf
uv run python experiments/<promoted-dir>/parse_corpus.py --reader liteparse
uv run python experiments/<promoted-dir>/build_indexes.py
uv run python experiments/<promoted-dir>/run_eval.py --resume
uv run python experiments/<promoted-dir>/summarise_eval.py
```

## 18. Required raw artefacts

- PDF manifest/checksums;
- parser invocation/runtime manifests;
- parser-specific extracted-text artefact checksums (text may remain gitignored if copyright/size requires, but identity must be recorded);
- per-PDF parse metrics;
- chunk/index build metrics;
- per-query P0/L0/P1/L1 raw results;
- paired/bootstrap analysis;
- parser failure table.

## 19. Interpretation rules

- H1 fail -> INVALID; do not call it a parser experiment.
- H2 fail -> parser quality superiority inconclusive; parser output/speed findings remain separately reportable.
- H3 fail -> do not promote LiteParse default on this corpus.
- H3 pass, H5 pass, no superiority -> LiteParse may be a speed/non-inferior option; default decision requires separate ADR criteria.
- H4 superiority + operational gates pass -> stronger candidate for default promotion, still via separate ADR/OpenSpec.
- reranker interaction changes sign -> investigate parser-specific candidate distributions rather than hiding it in aggregate.

## 20. Cleanup

Keep manifests, parser metrics, result JSON and reproducible acquisition instructions. Remove large PDF/index copies only when they can be reconstructed lawfully/reliably.
