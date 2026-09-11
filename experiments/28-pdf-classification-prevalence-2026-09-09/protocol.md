# Experiment 28 — PDF classification prevalence on a real library (task 5.5)

**ID**: `28-pdf-classification-prevalence-2026-09-09`
**Date planned**: 2026-09-09
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PLANNED (validity gates frozen 2026-09-09, before any measurement)
**Relation**: `improve-rag-input-quality-5` task 5.5; experiments 23 and 24

## Why this experiment exists

Experiment 23 calibrated the OCR routing gate on three synthetic fixtures.
Experiment 24 validated routing on five held-out fixtures, two of which
are pages rendered from a CC0 paper. Both passed. Neither answers the
question task 5.5 actually turns on:

> On documents a person really ingests, how often does this gate fire?

Nothing in this change has ever classified a real multi-page paper. The
packaged default for `OCR_FALLBACK_ENABLED` was about to be decided on
eight files, none of which came from a working library. This experiment
replaces that judgement call with a measurement.

**In plain terms:** run the classifier over a real paper library, count
how many papers it would send to OCR, and check none of them is a paper
that already has perfectly good text.

## Preregistration

Structured per `s-research/references/preregistration.md`, adapted for a
prevalence study. Deviations from that template are declared in
§Deviations rather than silently skipped.

### 1. Hypotheses

```
H1 (safety, confirmatory). The candidate gate routes ZERO documents that
   already carry a usable text layer, because pdf_type classification is
   driven by text-layer presence and the calibrated thresholds only
   qualify text_based PDFs that are already doubtful.
   Success: false_routing_count == 0.
   Failure: false_routing_count >= 1.

H2 (benefit, confirmatory). A resolvable minority of a working academic
   library genuinely lacks a usable text layer, because scanned
   photocopies, author manuscripts and older digitised articles persist
   in real collections.
   Success: Wilson 95% lower bound on needs_ocr prevalence > 0.01
            (at n=83, requires >= 3 documents).
   Failure: Wilson lower bound <= 0.01.
```

H1 is the promotion blocker. H2 decides whether promotion buys anything.

### 2. Foreknowledge of data

**Authors have observed a different dataset.** The eight fixtures under
`tests/fixtures/pdf_baseline/` have been classified, and their labels are
committed in that directory's `manifest.json` and in experiment 24's
`output/ablation.json`. Those observations informed the gates below.

**No document in the Zotero library has been classified by
pdf-inspector, and no aggregate over it has been computed.** The gates
are derived from the fixture evidence and from a power analysis
performed on n alone, never from the population under study.

One prior belief is on record and worth stating because this experiment
can falsify it: during this session the agent asserted that a mostly-text
paper containing one image-only page would classify `mixed` and send the
whole file to OCR. The one fixture that tests it (`eval_mixed.pdf`)
classified `text_based` at confidence 0.5 and stayed on the fast path,
contradicting the assertion. H1 tests it at scale.

### 3. Study design

Single-sample observational prevalence study. No manipulation, no
control arm, no random assignment: every document is classified once by
one classifier, and the routing decision is computed from that
classification by the production gate function.

This is deliberately not a system comparison. There is no second system
to compare against — the question is what one gate does to one
population.

### 4. Sampling

**Population**: the operator's curated Zotero library,
`~/Zotero/storage/**/*.pdf`, de-duplicated by content sha256. Expected
n ≈ 83.

**Rationale**: this is the corpus the operator would actually ingest for
research work, and it is the population the packaged default would act
on. It was chosen over a wider sweep of `~/Downloads`, `~/Documents` and
`~/Desktop` (n ≈ 300) by the operator.

**Sample size consequence, stated plainly.** n = 83 is a real limitation
and it weakens a clean result:

| n | Rule-of-three 95% upper bound if zero events | Smallest resolvable prevalence |
| ---: | ---: | ---: |
| 83 | 3.6% | 3 documents (3.6%) |
| 180 | 1.7% | 5 documents (2.8%) |
| 300 | 1.0% | 7 documents (2.3%) |

At n = 83, observing zero false routes bounds the true rate below 3.6%,
not below 1%. The conclusion must be written to that precision.

**Stopping rule**: every de-duplicated PDF in the population is
classified. There is no interim analysis and no early stop.

### 5. Variables

**Manipulated**: none.

**Measured**:

```
DV1: false_routing_count   — primary; documents with text that route anyway
DV2: needs_ocr_prevalence  — proportion with mean chars/page < 100
DV3: pdf_type distribution — text_based / scanned / image_based / mixed
DV4: confidence distribution and flagged-page proportion distribution
DV5: projected OCR wall-clock for the routed set
```

**Controlled**:

```
CV1: classifier      — pdf-inspector via the omrg registry
CV2: gate function   — ocr_required_by_gate, the production function
CV3: gate values     — enabled, min_confidence 0.5, page_fraction 0.5
CV4: no OCR          — no worker, no model load, no network
CV5: de-duplication  — content sha256
```

**Derived (ground truth)**: `needs_ocr_truth` = mean extracted characters
per page < 100. Pre-specified. The basis is measured, not assumed: the
two committed CC0 journal pages carry 3,934 and 4,150 characters each, so
100 characters per page is under 3% of a real page. Sensitivity at 50 and
200 characters per page is reported as exploratory.

### 6. Analysis plan

**Primary**: exact count of false routes. A count, not a test — H1 is a
zero-tolerance claim and any occurrence falsifies it.

**Interval estimation**: Wilson 95% intervals on every reported
proportion. Rule-of-three (3/n) upper bound for any zero-event count.
Wilson is used rather than the normal approximation because it stays
valid at proportions near 0, which is exactly where these estimates sit.

**No significance testing.** There is no comparison to test. Reporting a
p-value here would be decoration.

**Inclusion**: every readable PDF in the population.
**Exclusion**: files that fail to parse are reported separately with
their count and error class, never silently dropped. A parse failure is
a finding about the classifier, not a missing observation.
**Missing data**: none possible — the classifier is local and
deterministic.

**Exploratory (declared in advance, never gating)**: the character-density
sensitivity analysis; the relationship between page count and
classification; whether any document sits within 0.05 of either 0.5
threshold, which would show the calibration is load-bearing on this
population.

### 7. Deviations from the s-research preregistration template

Declared rather than skipped:

- **No Wilcoxon or paired testing.** The template assumes a system
  comparison with matched queries. This is single-sample prevalence
  estimation, where Wilson intervals and the rule of three are the
  correct instruments.
- **No corpus size tiers and no multi-domain matrix.** The template's
  §4.1 design principles serve generalisation across corpora. Here the
  population *is* the target of inference: the question is what this gate
  does to this operator's library, and sampling other domains would
  answer a different question.
- **No saturation check.** Saturation is a retrieval-metric concern. A
  prevalence has no ceiling to saturate against.
- **Underpowered by the template's standards, and it says so.** n = 83
  was the operator's scoping decision. The §4 table states exactly what
  that costs.

### 8. Privacy

The classifier reads file bytes. The committed artefacts must not leak
the library's contents.

- Document ids in committed output are sequential (`doc_001`, …).
- **No filename, no path, and no extracted text is ever written to a
  committed file.** Only page counts, character counts, classification
  labels, confidences and routing decisions.
- The id-to-path mapping is written to `output/.local_manifest.json`,
  which is gitignored and stays on the operator's machine.
- Preflight assertions enforce the first two points before any file is
  read.

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json).

| Gate | Rule | Basis |
| --- | --- | --- |
| Safety (H1) | `false_routing_count == 0` | Experiment 24 froze `altered_fast_path_outputs == 0` on the same principle. A false route costs 33.7–106.4 s/page against a ~1 s fast path: a 30–100× regression on a document that needed nothing. |
| Benefit (H2) | needs-OCR prevalence Wilson 95% lower bound > 0.01 | Power analysis at the realised n. At n = 83 this needs ≥ 3 documents; below that the study cannot separate a real need from noise. |

**Monitored, never gated:** projected OCR wall-clock (the operator's
tolerance is a preference, not a derivable number); the classification
distribution; and the routing count with the thresholds at their
never-trigger sentinels, which separates the unconditional `pdf_type`
rule from the calibrated thresholds.

## Decision rule, fixed in advance

| Outcome | Packaged default |
| --- | --- |
| H1 passes, H2 passes | `OCR_FALLBACK_ENABLED=true` with 0.5 / 0.5 is defensible |
| H1 passes, H2 fails | Ship 0.5 / 0.5 inert; switch stays `false` — harmless but nothing to gain |
| H1 fails | Promote nothing; the switch stays `false` whatever else holds |

**Scope limit, binding on the change record.** This experiment speaks for
one operator's curated academic library and nothing else. It cannot
license a default for corpora it never sampled, and the ADR must say so.

## Procedure

```bash
uv run python experiments/28-pdf-classification-prevalence-2026-09-09/classify.py
uv run python experiments/28-pdf-classification-prevalence-2026-09-09/summarise_eval.py
```

## Cost

Zero. No OCR worker, no model load, no API call, no embedding. Local
classification only, seconds to run.

## Artefacts expected

| File | Description | Required |
| --- | --- | :--: |
| `protocol.md` / `plan.json` | this preregistration + frozen gates | ✅ |
| `classify.py` / `summarise_eval.py` | runner chain | to write |
| `output/classifications.json` | per-document rows, anonymised | ✅ |
| `output/eval_results.summary.json` | gate checks, machine-readable | ✅ |
| `results.md` + `discussion.md` | outcome and interpretation | ✅ |
| `output/.local_manifest.json` | id → path map, **gitignored** | local only |
