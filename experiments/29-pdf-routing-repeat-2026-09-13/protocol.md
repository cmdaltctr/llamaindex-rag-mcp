# Experiment 29 — PDF routing repeat study (repeat-pdf-routing-study)

**ID**: `29-pdf-routing-repeat-2026-09-13`
**Date planned**: 2026-09-13
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PASS — gates evaluated 2026-09-13 (held-out recall vacuous, disclosed)
**Relation**: OpenSpec change `repeat-pdf-routing-study`; experiments 23, 24, 28; ADR-064; fix commit `9bf4810`

## Why this experiment exists

Experiment 28 measured the OCR routing gate on a real library and failed
both preregistered gates: one false route (a 991-page `mixed` book sent
wholly to OCR) and unresolvable needs-OCR prevalence. Its exploratory
analysis located the defect — `mixed` in `OCR_UNCONDITIONAL_TYPES` — and
commit `9bf4810` fixed it. ADR-064 kept `OCR_FALLBACK_ENABLED=false` and
deferred the promotion question to a preregistered repeat study.

Experiment 28 cannot be that evidence: its labels were classifier-derived
character counts, its corpus was a convenience scan, and its measurements
pre-date the fix. This study repeats the routing question under the
repaired evidence rules: an operator-approved collection, independent
page labels, a development/held-out split, and a pinned historical
baseline.

**In plain terms:** on documents a person approved in advance, does the
fixed policy send exactly the right files to OCR — and does the book
that broke experiment 28 stay on the fast path?

## Hypotheses

```
H1 (safety, confirmatory). The candidate gate routes ZERO held-out
   documents whose independent label says a usable text layer exists.
   Success: held_out false_routing_count == 0.
   Failure: held_out false_routing_count >= 1.

H2 (recall, confirmatory). The candidate gate misses ZERO held-out
   documents whose independent label says OCR is needed.
   Success: held_out missed_needs_ocr_count == 0.
   Failure: held_out missed_needs_ocr_count >= 1.
```

Development outcomes are regression checks, not evidence for H1/H2:
a pass on the book confirms the fix addresses the known failure; it
does not validate the rule on unseen documents.

## Foreknowledge of data

The three experiment-28 documents are known and are all development
evidence:

- the book — `mixed`, 991 pages, 10 flagged, ~1,127 chars/page — false-routed
  under the pre-fix policy;
- the scanned Kerr (1998) paper — 23 pages, 0 chars/page — correctly routed;
- the Sloman (1971) paper — `text_based` at confidence 1.0, zero extractable
  text — caught only by the calibrated page-fraction threshold.

Held-out documents must not have been examined during candidate design.
The candidate itself is already fixed in committed code (`9bf4810`); this
study does not design a new rule, it validates the committed one. Should
held-out evidence motivate a *further* candidate, that candidate is a new
question and needs a new freeze — it cannot borrow this study's held-out
set.

## Study design

Policy comparison on an approved collection. Each document is classified
once by `pdf-inspector`; the routing decision is then replayed under four
policies through the production gate function `ocr_required_by_gate`:

| Arm | Unconditional types | Thresholds | What it answers |
| --- | --- | --- | --- |
| `baseline_exp28` | `scanned, image_based, mixed` (pinned at `afe151e`, extracted via `git show`) | 0.5 / 0.5 | Experiment 28's exact arm, replayed on this collection |
| `baseline_matched` | `scanned, image_based, mixed` (same pin) | 0.5 / 0.10 | Isolates `9bf4810`: differs from the candidate only in the unconditional set |
| `candidate` | `scanned, image_based` (committed code) | 0.5 / 0.10 | The approved candidate under test |
| `enable_only` | `scanned, image_based` | 0.0 / 0.0 sentinels | What happens when only `OCR_FALLBACK_ENABLED` is set |

The pinned arms are reconstructed from the pinned revision's source and
verified against the frozen plan at preflight; the working tree is never
an unnamed baseline. `routed_baseline_matched` vs `routed_candidate` is
the measured effect of `9bf4810`; `routed_baseline_exp28` vs
`routed_baseline_matched` isolates the tolerance change to 0.10.

## Sampling

**Population** (approved 2026-09-13): 17 documents in
`output/.collection.private.json` (gitignored):

- **Development (3)**: the experiment-28 book, the scanned Kerr (1998)
  paper, and the Sloman (1971) paper.
- **Held-out (14)**: every PDF attachment in the operator's Zotero `RAG`
  collection.

**Held-out disclosure**: all 14 held-out documents were inside
experiment 28's scanned corpus. Their classification evidence predates
this freeze, but none routed under the baseline and none were examined
individually during candidate design; their independent labels are new
evidence. If a held-out outcome ever motivates a redesign, that document
is promoted to development evidence and the held-out set shrinks — it can
never go back.

**Known asymmetry, disclosed**: no held-out document carries
`needs_ocr=true`, so the recall gate is untestable on held-out evidence.
The development split carries the recall check (Kerr and Sloman must
route); the report states this limit plainly.

**Scope limit**: this is a selected collection, not a prevalence sample.
Results are reported for this collection only; no claim about academic
libraries in general is licensed.

## Variables

**Manipulated**: routing policy (three arms above).

**Measured**:

```
DV1: routed_<arm> — per document, for each of the four arms
DV2: false_routing_count / missed_needs_ocr_count per policy × split
DV3: pdf_type, confidence, flagged-page count, page count, chars/page
DV4: classification_seconds — measured per document
DV5: projected_ocr_seconds — routed pages × 106.4 s, a PROJECTION
```

**Controlled**: classifier (`pdf-inspector`), gate function (production),
no OCR worker, no model load, no network, no ingestion.

**Ground truth**: `labels.json` — independent page assessment. Each
label records whether important text is readable and whether extraction
misses content. All flagged pages are inspected plus an agreed sample of
unflagged pages; uncertain cases are labelled `uncertain` and reported.
Aggregate character counts are supporting evidence, never the sole label.

## Analysis plan

- False-route and missed-need counts per policy, reported separately for
  development and held-out splits. Gates evaluate held-out only.
- Wilson 95% interval on held-out needs-OCR prevalence, reported as
  descriptive, never as a population estimate.
- Baseline-vs-candidate divergence table: every document where the two
  arms disagree.
- Projected OCR cost in both directions: pages routed that needed
  nothing, and pages not routed that needed OCR.
- No significance testing — counts against zero-tolerance gates.

**Gate evaluability**: gates are evaluated only when `labels.frozen` is
true and every held-out document is labelled. Otherwise the summary
reports the run as measurement without a verdict.

## Privacy

- Public artefacts carry `doc_id`, `sha256`, split and measurements only.
- Paths live in `output/.collection.private.json` and
  `output/.local_manifest.json` (gitignored); exception text lives in
  `output/.errors.private.json` (gitignored). Public error rows carry the
  exception class only.
- `_assert_no_private_leak` walks every string leaf of the checkpoint
  before each write and refuses to persist a registered private string.
- The public collection manifest is written once; a drifted collection
  cannot overwrite it.

## Recorded approvals (decision register, 2026-09-13)

| Item | Decision |
| --- | --- |
| Approved collection list (incl. the book) | APPROVED — 3 dev + 14 held-out as above |
| Page-annotation method + dev/held-out split | APPROVED — independent pypdf per-page assessment; split as above |
| Missing-page tolerance | 10% of pages without usable text warrants whole-document OCR (candidate `page_fraction=0.10`) |
| Whole-document routing behaviour | Whole-file dispatch accepted — no page stitching exists |
| Enable-only zero-threshold expectation for `mixed` | Stays on the fast path (classification-only routing) |
| Real OCR authorisation | NOT authorised — classification and replay only; OCR costs are projections, recovery quality unmeasured |

## Frozen validity gates

| Gate | Rule | Basis |
| --- | --- | --- |
| Safety (H1) | held-out `false_routing_count == 0` | Experiments 24/28 zero-tolerance precedent; a false route costs 30–100× per page |
| Recall (H2) | held-out `missed_needs_ocr_count == 0` | A default that misses textless documents preserves the gap it exists to close |
| Dev recall check | dev_002 and dev_003 route under the candidate | The only needs-OCR documents in the collection; a miss here fails promotion regardless of H2's untestability |

## Decision rule, fixed in advance

| Outcome | Interpretation |
| --- | --- |
| H1 passes AND dev_002/dev_003 route under the candidate | The candidate is safe on this collection; promotion remains a separate decision. H2 is reported as untested (no held-out needs-OCR document exists) |
| H1 fails, or a dev recall check misses | Promote nothing; the switch stays `false` |
| No held-out evidence | INCONCLUSIVE — development regression checks are reported without a verdict |

## Procedure

```bash
# after approvals are recorded in the change's decision register:
uv run python experiments/29-pdf-routing-repeat-2026-09-13/prepare_collection.py \
  --development <approved paths> --held-out <approved paths>
# freeze commit: plan.json + labels.json + collection.public.json + this file
uv run python experiments/29-pdf-routing-repeat-2026-09-13/classify.py
uv run python experiments/29-pdf-routing-repeat-2026-09-13/summarise_eval.py
```

## Cost

Classification-only: zero — local, deterministic, seconds. Real OCR is a
separately authorised phase with named documents, a timeout and a runtime
budget; without it, all OCR cost figures are labelled projections and
recovery quality is reported as unmeasured.

## Artefacts expected

| File | Description | Required |
| --- | --- | :-: |
| `protocol.md` / `plan.json` | preregistration + frozen gates | ✅ |
| `labels.json` | frozen independent page labels | ✅ before scoring |
| `prepare_collection.py` / `classify.py` / `summarise_eval.py` | runner chain | ✅ |
| `output/collection.public.json` | doc_id + sha256 + split manifest | ✅ |
| `output/classifications.json` | per-document rows + run identity | ✅ |
| `output/eval_results.summary.json` | gate checks, machine-readable | ✅ |
| `results.md` | outcome, interpretation and conclusion (single document) | ✅ |
| `output/.collection.private.json` etc. | private mappings | local only |
