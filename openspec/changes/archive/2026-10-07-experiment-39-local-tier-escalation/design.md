# Design

## Context

- **What ships.** ADR-069 decision 2: after the local attempt, a page escalates on empty text, confidence below `OCR_LOCAL_MIN_CONFIDENCE` (0.8), an unreported confidence, or `hosted_recommended` (`integrations/pdf/page_routing.py`). The operator's 2026-09-18 amendment dropped a script and typography *pre-check*, because no measured signal predicted the failures before the attempt.
- **What ADR-069 already covers.** The confidence candidate of this experiment is the shipped post-check. This experiment adds a script signal read from the local OCR *output*, after the attempt, so the amendment still holds. The `io06` blind spot is named in ADR-069 as an accepted residual.
- **What the data holds.** `pages.json` has 464 rows: 399 with frozen body label `needs_ocr`, 61 `usable` and 4 `ambiguous` (figure-only need). Each row has `body_recall`, `confidence`, `hosted_recommended`, `chars` and `warnings`. The page text is saved in `output/.local_ocr_text/<doc>/p<NNN>.md` (464 files).
- **Scripts, corrected.** The reference transcriptions show `io01` Devanagari (48 pages), `io02` and `io03` Arabic (21), `io07` Bengali (60). ADR-071 carries an erratum.
- **What the output looks like on those pages.** The packaged model recognises Chinese, Japanese and English only. On Devanagari and Bengali pages it emits CJK characters and Latin fragments. On Arabic pages it emits mostly Latin fragments. The pages have no text layer. So a Unicode-block check cannot read the true script from the input, and it cannot see Arabic in the output. It can see a script the corpus does not contain.
- **Prior look, disclosed.** While planning, the author counted letters by Unicode block over the saved text of 7 documents, pooled per document (not per page, and with no candidate scored): `io07` 4,226 CJK of about 4,745 letters, `io01` 764 CJK of about 2,197, `io06` 6 CJK of 53,949, `rf06` 3 of 24,585, `mx01` 0 of 2,198.
- **An error in ADR-069 found while planning.** Line 31 says 11.3% of kept pages fall below 0.5 recall. Line 115 says "below 0.8". The Experiment 33 calibration table supports 0.5.

## Goals / Non-Goals

**Goals:**

- Test whether a script-mismatch post-check, alone or with the confidence cut, keeps zero unreadable non-Latin pages at an acceptable escalation cost.
- State whether any signal in the rows separates `io06`.

**Non-Goals:**

- New OCR, a new model, or a per-line confidence export. These need a new protocol and operator approval.
- Choosing the local model for Arabic, Devanagari or Bengali. Experiment 37 measures the OCR engines on these pages.
- Changing `OCR_LOCAL_MIN_CONFIDENCE` or any default.

## Decisions

### D1. Population

The gated population is the 399 rows with body label `needs_ocr`, the same population as the Experiment 33 calibration table (escalation 0.469 and kept-below-0.5 share 0.113 at the 0.8 cut). The 65 figure-only rows are reported as a diagnostic.

### D2. Candidates

| ID | Rule (escalate the page when …) |
| --- | --- |
| C0 | the shipped post-check: empty text, confidence below 0.8 or unreported, or `hosted_recommended` |
| C1 | CJK share ≥ 0.05: letters in CJK Unified Ideographs (all extensions), Hiragana, Katakana or Hangul, divided by all letters in the page output. Empty output also escalates |
| C3 | C0 or C1 |
| Sweep | C0 with the cut at 0.5, 0.6, 0.7, 0.8 and 0.9 (reported, not gated except 0.8) |
| C4 | exploratory: discarded-region count from `warnings`, and characters per page, as `io06` separators (AUC only) |

C1 threshold, 0.05: the corpus holds no CJK document, so CJK letters in the output are misreadings. In Latin-script documents the prior look found stray CJK at about 0.0001 of letters. 0.05 sits 500 times above that and far below the shares seen on Devanagari and Bengali output. The rule works only while the operator's documents contain no CJK. A production version needs a declared-scripts setting, which this corpus cannot test.

### D3. Pass criteria (fixed before the run)

| Gate | Rule | Reason |
| --- | --- | --- |
| G1 | 0 of the 129 non-Latin pages (`io01`, `io02`, `io03`, `io07`) kept | local recall is 0.000 on every one; a kept page indexes junk for certain (ADR-071 decision 4) |
| G2 | kept pages with body recall < 0.5 ≤ 0.05 of kept pages, on the population without `io06` | halves ADR-069's accepted 0.113; the 0.9 confidence cut already reaches 0.025, so the bound is reachable and the question is cost |
| G3 | escalated share ≤ O + 0.05, where O is the share of the 399 pages with body recall < 0.5 | a rule that keeps no bad page must escalate at least O; 0.05 (about 20 pages) is the allowance for wasted worker calls, about 13 min at dots.mocr's 38.2 s per page. On Experiment 33 figures O is about 0.52, so the bound (about 0.57) sits below the 0.9 cut's 0.597: a passing rule must be cheaper than raising the cut |

`io06` is outside G2 because ADR-071 decision 4 says it needs an engine signal, and the only engine signals in the rows are confidence, `hosted_recommended` and the discarded-region count. Its kept-bad share is reported beside G2 in every table. O is computed from the labels, not from any candidate, so it is fixed before the run.

**Selection:** among the candidates that pass G1 to G3, the one with the lowest escalated share wins. A tie goes to the simpler rule (C0, then C1, then C3).

### D4. Script detection helper

A pure function maps each letter (`str.isalpha`) to a script group through `unicodedata.name` prefixes, with CJK Unified Ideographs, Hiragana, Katakana and Hangul in one group. Unit tests use fixed strings, including the saved `io07` fragment style (CJK mixed with Latin) and a clean Spanish line.

## Risks / Trade-offs

- [The prior look saw pooled Unicode counts] → disclosed above. The threshold follows from the stray rate in Latin documents, not from the non-Latin pages, and the gates are fixed now.
- [C1 cannot see Arabic output, which comes out as Latin fragments] → C3 relies on the confidence cut for Arabic. If C3 fails G1 only on Arabic pages, the next candidate is the Experiment 38 text-quality signal on the local output.
- [C1 would escalate every page of a real CJK document] → stated as a limit. A production rule needs a declared-scripts setting.
- [`io06` stays unsolved] → reported apart, with the engine output a future rule needs (per-line or per-character confidence spread).

## Open Questions

None. The run needs no approval: no OCR, no download, no new package.
