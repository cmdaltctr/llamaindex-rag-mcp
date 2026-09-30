# Experiment 37: dots.mocr routing acceptance on real documents

- **ID**: `37-dots-mocr-routing-acceptance-2026-09-30`
- **Date planned**: 2026-09-30
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Claude Code (plan)
- **Status**: PLANNED (blocked on the engine build and on operator OCR authorisation)
- **Relation**: OpenSpec change `modular-ocr-workers-dots-mocr`, tasks 7.1 to 7.3; Experiment 34 (A2, A4); Experiment 33 task 6.7; ADR-071 decision 7
- **Plan**: [`plan.json`](plan.json) (page lists, gates, budget and authorisation block)

## Why this experiment exists

The operator made dots.mocr the primary OCR engine on 2026-09-24 from Experiment 34 evidence: 5 pages, one maths page (`eq01` p11) and two old-book pages. That evidence was enough to decide. It is not enough to accept the built system. This experiment is the acceptance check the change names in section 7. It does not gate the engine decision.

Three questions stay open after Experiment 34:

1. Does the new maths-font detector flag the pages that carry maths, and only those?
2. Does dots.mocr emit formulas that render, and does it invent text on scanned pages? Experiment 34 saw bleed-through noise on `io06` p53.
3. How do both engines read the writing systems the local tier cannot read? The local tier scored median token recall 0.000 on Arabic, Devanagari and Bengali pages, and 0.310 on handwriting (Experiment 33 task 6.7).

## Hypotheses

1. **H1 (detection, negative controls).** The detector flags zero pages in the negative-control set.
2. **H2 (converter).** At most 5% of the formulas dots.mocr emits on the maths and scanned sets fail to render in KaTeX 0.16.22.
3. **H3 (noise, operator review).** The operator accepts the list of pages where either engine emits text that is not on the page image.
4. **Q4 (reported, not gated).** dots.mocr and PaddleOCR-VL token recall on the script and handwriting set, by writing system, beside the Experiment 33 local-tier recall.

## Background and prior evidence

- Experiment 34 report: `experiments/34-worker-sample-review-2026-09-19/report.md`. dots.mocr was the operator's best output on all 5 pages it ran. Median 38.2 s per page on MPS (n = 43 page runs, maximum 137.5 s).
- Experiment 33 report: `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`, task 6.7 table.
- Change design: `openspec/changes/modular-ocr-workers-dots-mocr/design.md`, D4 (engine) and D5 (detector patterns).

### Correction to the script set description

Task 7.1 and ADR-071 describe `io01`, `io02` and `io03` as Arabic and `io07` as Hindi. The Experiment 33 reference transcriptions show otherwise (letters counted by Unicode block, 2026-09-30):

| Document | Script in the reference transcription | `needs_ocr` body pages |
| --- | --- | ---: |
| `io01` | Devanagari (Hindi) | 48 |
| `io02` | Arabic | 16 |
| `io03` | Arabic | 5 |
| `io07` | Bengali | 60 |
| `rf06` | Latin handwriting (Spanish) | 43 |
| `rf07` | Latin handwriting (Spanish) | 17 |

The page set does not change. Only the writing-system grouping changes. This protocol reports four groups: Devanagari (48), Arabic (21), Bengali (60) and Latin handwriting (60). Total: 189 pages.

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | OCR engine | `dots-mocr` (primary route), `paddleocr-vl` (fallback route) |
| Independent | Detector input | every page of the maths-positive and negative-control PDFs |
| Dependent | Detection | per-page flag against the operator's maths label |
| Dependent | Formula validity | KaTeX 0.16.22 render error rate over emitted formulas |
| Dependent | Invented text | pages where an engine emits text absent from the page image |
| Dependent | Token recall | multiset token recall against the Experiment 33 reference, Experiment 33 token rule |
| Diagnostic | Cost | seconds per page, peak MPS memory, per engine |
| Controlled | Engine builds | pinned revisions and fingerprints recorded at freeze time |
| Controlled | Labels | Experiment 33 frozen labels and reference transcriptions. No relabelling |

Not changed: the OCR gate thresholds (`0.5`, `0.10`), the local tier (PP-OCRv6 Small), `OCR_MATHS_PAGE_FRACTION` (0.10).

## Corpus and ground truth

PDFs sit in gitignored `corpus/`. Provenance and hashes go in `sources.json`.

| Set | Contents | Pages | Ground truth | Status |
| --- | --- | ---: | --- | --- |
| Maths positives | at least 5 arXiv maths-heavy papers from different fields and years. One is pdfLaTeX with `glyphtounicode` (Unicode-mapped maths font). One is a Word paper with Cambria Math. | all pages for detection; up to 8 maths pages per paper for engines (seed 37) | operator page label `maths` / `no_maths` from the page image | to source |
| Negative controls | Experiment 34 `bd01`, `bd02`, `bd03`; one prose-only LaTeX paper | all pages, detection only | every page is `no_maths` by construction; the operator confirms the prose-only paper | to source (prose paper) |
| Scanned set | Experiment 34 sampled pages of `io04` (12), `io06` (12), `tl03` (4) | 28 | operator review of noise (H3) | page list frozen in `plan.json` |
| Script and handwriting set | Experiment 33 pages whose frozen body label is `needs_ocr` in `io01`, `io02`, `io03`, `io07`, `rf06`, `rf07` | 189 | Experiment 33 reference transcriptions (`output/.transcripts`, body split in `output/.transcripts_split`) | page list frozen in `plan.json` |

**Maths label rule.** A page is `maths` when its image shows at least one mathematical expression typeset as mathematics: a display equation, or an inline expression with a variable, operator or Greek letter. Section numbers and plain numerals are not maths. The operator labels every page of the maths positives and the prose-only control before the run. The labels are frozen with a SHA-256 in `plan.json`.

**Experiment 33 preconditions.** Run `uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/freeze.py --check` before any read of an Experiment 33 label. It must print `freeze verified`. On 2026-09-30 it did. `labels.json` is tracked at commit `cf0d6d7`.

## Environment and prerequisites

| Requirement | Value |
| --- | --- |
| OMRG | branch with `modular-ocr-workers-dots-mocr` sections 0 to 6 merged |
| dots.mocr engine | `ocr-workers/engines/dots-mocr/`, provisioned with `--accept-model-licence` by the operator, pinned revision `e539fbb52280393adc081b289ec597430a0f9031` |
| PaddleOCR-VL engine | `ocr-workers/engines/paddleocr-vl/`, provisioned |
| Hardware | operator's Apple Silicon Mac, MPS, bfloat16 for dots.mocr; CPU for PaddleOCR-VL |
| KaTeX | 0.16.22, Node, `throwOnError: true`, `displayMode` per formula |
| Network | off during engine runs (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) |

## Design

| Run ID | Purpose | Input | Engines |
| --- | --- | --- | --- |
| `D-pos` | detection recall and precision | every page of the maths positives | detector only |
| `D-neg` | H1 | every page of the negative controls | detector only |
| `E-maths` | H2, H3, cost | labelled maths pages (up to 8 per paper, seed 37) | both, page-listed requests |
| `E-scan` | H2, H3, cost | 28 scanned-set pages | both |
| `E-script` | Q4, cost | 189 script and handwriting pages | both |

Each engine runs through the built host path (`OcrRoutes` with the engine named as primary). The run does not call the engine package directly. This tests the route, the timeout scaling and the Markdown convergence, as well as the model.

Checkpoint after each document. Write each page's Markdown to `output/<engine>/<doc_id>/p<NNN>.md` atomically (`.tmp`, then rename). `--resume` skips finished pages.

## Metrics

### Primary (gated)

- **Negative-control flags**: flagged pages in `D-neg`. Gate: 0.
- **KaTeX error rate (dots.mocr)**: formulas that fail to render ÷ formulas emitted, over `E-maths` and `E-scan`. A formula is each `$$…$$` block and each `$…$` inline span in the emitted Markdown. Gate: ≤ 0.05.
- **Noise list review**: pages where the operator marks emitted text as absent from the page image, per engine. Gate: the operator records a verdict for every listed page.

### Reported (not gated)

- Detection precision and recall per page on `D-pos`, flagged share per paper, and every font name on `maths`-labelled pages that `MATHS_FONT_PATTERNS` does not match.
- PaddleOCR-VL KaTeX error rate, for comparison.
- Token recall per page on `E-script`, median and share ≥ 0.8 and < 0.5, per writing system and engine, beside the Experiment 33 local-tier values (from `output/local_ocr/pages.json`, same pages). Tokeniser: `build_labels.tokens` from Experiment 33, imported, not copied.
- Seconds per page and peak MPS memory per engine.

## Procedure

1. Source the maths positives and the prose-only paper. Record URL, licence, arXiv version and SHA-256 in `sources.json`.
2. The operator labels every page of those PDFs (`maths` / `no_maths`) from the page images. Freeze the labels (SHA-256 into `plan.json`).
3. Record the built system identity in `plan.json`: OMRG commit, `MATHS_DETECTOR_VERSION`, both engine fingerprints, KaTeX version.
4. The operator fills the authorisation block in `plan.json` (subset, timeout, runtime budget) and accepts the dots.mocr licence at provisioning.
5. Run `D-pos` and `D-neg`. These are host-only and need no OCR.
6. Run `E-maths`, `E-scan`, then `E-script`, dots.mocr first, then PaddleOCR-VL.
7. Summarise into `output/summary.json`. Build the noise review page for the operator.
8. The operator reviews the noise list. Write `report.md`.

## Success criteria

| Gate | Rule | Source |
| --- | --- | --- |
| G1 | 0 flagged pages in `D-neg` | task 7.3 |
| G2 | dots.mocr KaTeX error rate ≤ 0.05 | task 7.3 |
| G3 | operator verdict recorded for every page on the noise list | task 7.3 |

Q4 is reported, not gated (task 7.3).

## Interpretation rules

- If G1 or G2 fails, fix the detector or converter, bump its version, and repeat the affected runs (task 7.3). Each repeat is an amendment in `plan.json`.
- A failure of G1 caused by one font family is fixed in the pattern list. A failure caused by a font name shared by maths and text fonts goes to the operator. It may need a different signal.
- Q4 informs AIE-100 (Experiment 39) and AIE-29 (Arabic and multilingual validation). It does not change the engine decision.
- Unmatched maths font names are a finding, not a failure. The report lists them.

## Runtime budget (estimate, for the operator's authorisation)

| Run | Pages per engine | dots.mocr at 38.2 s median | PaddleOCR-VL at 23 to 164 s |
| --- | ---: | ---: | ---: |
| `E-maths` | up to 40 | about 25 min | 15 min to 1.8 h |
| `E-scan` | 28 | about 18 min | 11 min to 1.3 h |
| `E-script` | 189 | about 2.0 h | 1.2 h to 8.6 h |
| **Total** | **up to 257** | **about 2.7 h** | **1.6 h to 11.7 h** |

Rates come from Experiment 34: dots.mocr median over 43 page runs on MPS; PaddleOCR-VL per-page rates of its full-document runs (`io06` 23 s, `io04` 142 s, `bd01` 164 s) on CPU. If the operator caps the budget, `plan.json` names a fallback: a seeded (seed 37) subsample of up to 30 pages per writing system in `E-script` (111 pages).

## What cannot be finished before the engine build

- Steps 3 to 8 need the built system: the detector (task 5.1), the routes (task 4.2), and both engines provisioned.
- The engine identity and fingerprints in `plan.json` are placeholders until then.
- Provisioning dots.mocr needs the operator's `--accept-model-licence` and a 5.7 GB download. Both are operator decisions.
- Steps 1 and 2 (sourcing and maths labels) can run before the build. They need the operator for labelling, and approval to download the papers.

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan; page lists, gates, budget, authorisation |
| `sources.json` | provenance of the new PDFs |
| `maths_labels.json` | operator page labels, frozen |
| `output/detection.json` | per-page flags and font names |
| `output/<engine>/…` | per-page Markdown (gitignored) |
| `output/pages.json` | per-page rows: seconds, formulas, KaTeX errors, recall |
| `output/summary.json` | gates and reported values (committed) |
| `report.md` | verdict and the operator's noise review |

## References

- `openspec/changes/modular-ocr-workers-dots-mocr/tasks.md` section 7
- `experiments/34-worker-sample-review-2026-09-19/report.md`, `sample.json`, `output/dots_mocr_state.json`, `output/worker_state.json`
- `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`, `labels.json`, `output/local_ocr/pages.json`
- `docs/adr/071-ocr-routing-natural-positive-findings.md`
