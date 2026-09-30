# Experiment 39: Local OCR tier escalation on script and typography

- **ID**: `39-local-tier-escalation-2026-09-30`
- **Date planned**: 2026-09-30
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Claude Code (plan)
- **Status**: PLANNED (ready to run; no approval needed)
- **Relation**: OpenSpec change `experiment-39-local-tier-escalation`; ADR-071 decision 4 and erratum; ADR-069 decision 2; NiftyPM AIE-100
- **Plan**: [`plan.json`](plan.json)

## Why this experiment exists

The local OCR tier reads modern Latin print well (median token recall 0.977) and fails on everything else: 0.000 on all 129 non-Latin pages, 0.310 on handwriting, and 0.609 on the early-modern book `io06`, where its median confidence is 0.922. The shipped post-check (ADR-069) escalates a page on empty text, confidence below 0.8, or `hosted_recommended`. At that cut, 11.3% of kept pages still fall below 0.5 recall. ADR-071 decision 4 asks for a rule that keeps no page the local model cannot read.

## What ADR-069 and `page-level-ocr-routing` already cover

- **The confidence cut is shipped.** Candidate C0 below is the exact post-check in `integrations/pdf/page_routing.py` (`OCR_LOCAL_MIN_CONFIDENCE=0.8`). This experiment uses it as the baseline.
- **A script pre-check was considered and dropped.** The operator's 2026-09-18 amendment removed it, because no measured signal predicted the failures before the attempt. This experiment tests a script signal on the OCR *output*, after the attempt, which the amendment allows.
- **`io06` is an accepted residual in ADR-069.** This experiment reports it apart and looks for an engine signal in the existing rows.
- **Not covered by either:** Bengali. ADR-071 named Arabic and Devanagari only. `io07` is Bengali (ADR-071 erratum, 2026-09-30).
- **A wording slip in ADR-069.** Line 31 says 11.3% of kept pages fall below 0.5 recall. Line 115 says "below 0.8". The Experiment 33 table supports 0.5.

## Hypotheses

1. **H1.** C3 (C0 or C1) keeps zero non-Latin pages and passes G2 and G3.
2. **H2.** C1 alone passes G1.
3. **Q3 (exploratory).** The discarded-region count or characters per page separates `io06` pages with recall below 0.5 from modern-print pages with recall of 0.8 or more.

## Data

| Item | Value |
| --- | --- |
| Rows | `experiments/33-ocr-routing-natural-positive-2026-09-17/output/local_ocr/pages.json`, 464 rows |
| Text | `experiments/33-…/output/.local_ocr_text/<doc>/p<NNN>.md`, 464 files (gitignored) |
| Engine | pdf-inspector 1.17.0, `pp-ocrv6-small@oar-ocr-v0.7.0`, onnxruntime 1.28.0, `force` mode |
| Ground truth | each row's `body_recall`: token recall of the local output against the frozen body reference |
| Gated population | 399 rows with frozen body label `needs_ocr` |
| Diagnostic population | 65 figure-only rows (61 `usable`, 4 `ambiguous` body labels) |
| Precondition | `freeze.py --check` prints `freeze verified` |

Non-Latin pages in the gated population: `io01` Devanagari 48, `io02` Arabic 16, `io03` Arabic 5, `io07` Bengali 60. Total: 129. `io06` holds 66 rows.

**O**, the share of the 399 pages with body recall below 0.5, is 0.516 (computed on 2026-09-30 from the rows. It is ground truth, not a candidate score).

**Prior look, disclosed.** While planning, the author counted letters by Unicode block over the saved text of 7 documents, pooled per document: `io07` 4,226 CJK of about 4,745 letters, `io01` 764 of about 2,197, `io06` 6 of 53,949, `rf06` 3 of 24,585, `mx01` 0 of 2,198. No candidate was scored per page.

## Candidates

| ID | Escalate the page when … |
| --- | --- |
| C0 | shipped post-check: empty or whitespace text, confidence below 0.8 or unreported, or `hosted_recommended` |
| C1 | output CJK share ≥ 0.05 (letters in CJK Unified Ideographs and extensions, Hiragana, Katakana, Hangul ÷ all letters), or empty output |
| C3 | C0 or C1 |
| Sweep | C0 at cuts 0.5, 0.6, 0.7, 0.8, 0.9 (reported; only 0.8 is gated as C0) |
| C4 | exploratory, not gated: discarded-region count (parsed from `warnings`) and characters per page, AUC for `io06` recall < 0.5 against modern print recall ≥ 0.8 |

Why CJK: the packaged model recognises Chinese, Japanese and English. On Devanagari and Bengali pages it writes CJK characters. The corpus has no CJK document, so any CJK output is a misreading. Why 0.05: stray CJK in Latin-script output is about 0.0001 of letters. 0.05 sits 500 times above it.

Limits: C1 cannot see Arabic output, which comes out as Latin fragments. C1 would escalate every page of a real CJK document, so a production version needs a declared-scripts setting.

## Success criteria (fixed before the run)

| Gate | Rule | Reason |
| --- | --- | --- |
| G1 | non-Latin pages kept = 0 of 129 | local recall 0.000 on every one; a kept page is junk for certain |
| G2 | kept pages with body recall < 0.5 ÷ kept pages ≤ 0.05, without `io06` (333 pages) | halves ADR-069's accepted 0.113; the 0.9 cut already reaches 0.025, so the bound is reachable and the question is cost |
| G3 | escalated share ≤ 0.566 (O + 0.05) | any rule that keeps no bad page escalates at least O = 0.516; 0.05 is about 20 wasted worker calls (about 13 min at dots.mocr's 38.2 s per page). The bound is below the 0.9 cut's 0.597, so a passing rule must cost less than raising the cut |

The kept-bad share with `io06` included is reported beside G2 for every candidate.

**Selection:** among passing candidates, the lowest escalated share wins. A tie goes to the simpler rule: C0, then C1, then C3.

## Procedure

1. Run `uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/freeze.py --check`.
2. Load the 464 rows and 464 texts. Check the counts in the Data table.
3. Score every rule. Write `output/rules.json`.
4. Check reproduction: C0 must give escalation 0.469 and kept-below-0.5 share 0.113 within 0.001 (Experiment 33 calibration table). Stop if it does not.
5. Summarise into `output/summary.json`: O, per-rule gates, per-document escalation, the `io06` column, and C4 AUCs.
6. Write `report.md`.

No OCR, no download, no package install. Standard library only.

## Interpretation rules

- C0 passes every gate: the shipped rule is enough. Record it and close ADR-071 decision 4 for the non-Latin class.
- C3 passes and C0 fails: propose adding the CJK post-check to `page_routing.py`, with a declared-scripts setting.
- Only the Arabic pages fail G1 for C3: the next candidate is the Experiment 38 text-quality signal on the local output.
- C4 separates `io06` (AUC ≥ 0.8): propose a follow-up protocol for that signal. Otherwise the report names the engine output a future rule needs: per-line or per-character confidence spread, which needs a new local OCR run and operator approval.

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan |
| `score_rules.py`, `test_score_rules.py`, `summarise_eval.py`, `analysis.py` | scripts |
| `output/rules.json` | per-page decision per rule |
| `output/summary.json` | gates and diagnostics (committed) |
| `report.md` | verdict |

## References

- `docs/adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md`
- `docs/adr/071-ocr-routing-natural-positive-findings.md`, decision 4 and erratum
- `openspec/changes/archive/2026-09-28-page-level-ocr-routing/tasks.md` (task 4.2a)
- `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`, local OCR tier section
- `experiments/37-dots-mocr-routing-acceptance-2026-09-30/protocol.md` (`E-script` covers the same non-Latin pages)
