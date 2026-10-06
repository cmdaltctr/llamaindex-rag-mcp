# Experiment 39: Local OCR tier escalation on script and typography

- **ID**: `39-local-tier-escalation-2026-09-30`
- **Date run**: 2026-10-06
- **Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
- **Status**: FAIL. No candidate passes gates G1 to G3.
- **Verdict**: No winning rule. The shipped post-check (C0) keeps one non-Latin page. The script rule (C1) keeps 19. The combination (C3) matches C0. The `io06` blind spot stays open.
- **Raw data**: [`output/rules.json`](./output/rules.json), [`output/summary.json`](./output/summary.json)
- **Change**: `openspec/changes/experiment-39-local-tier-escalation`; ADR-071 decision 4; ADR-069 decision 2; NiftyPM AIE-100
- **Protocol**: [protocol.md](protocol.md), [plan.json](plan.json)

## Bottom line

The shipped confidence cut (0.8) is still the best rule in the data that costs less than raising the cut to 0.9. No rule keeps zero unreadable non-Latin pages and stays inside the escalation budget.

- C0 keeps one Arabic page (`io02` p13, confidence 0.8046, 0.0046 above the cut). G1 fails.
- C1 reads the output script. It sees Devanagari and Bengali output as CJK and escalates 105 of 108 of those pages. It cannot see Arabic, because the model writes Arabic as Latin fragments. It keeps 16 of 21 Arabic pages.
- C3 escalates one page more than C0 (`tl02` p33, recall 0.80, a good page).
- G2 fails for every rule that passes G1 except the 0.9 cut. The 0.9 cut passes G1 and G2 and fails G3: it escalates 0.596 against a bound of 0.566.

No production change follows. Task 4.3 asks for a separate proposal only if a rule other than C0 wins. None won, so no proposal was opened and no proposal id exists.

## What we tested

Eight rules, scored per page on the 464 saved local OCR results of Experiment 33 (PP-OCRv6 Small, ONNX Runtime, CPU). No new OCR ran. The gated population is the 399 pages with frozen body label `needs_ocr`.

| Rule | Escalate the page when |
| --- | --- |
| C0 | text is empty, confidence is below 0.8 or missing, or `hosted_recommended` (shipped, ADR-069) |
| C1 | CJK share of letters is 0.05 or more, or text is empty |
| C3 | C0 or C1 |
| C0@cut | C0 with the cut at 0.5, 0.6, 0.7, 0.8, 0.9 (reported; only 0.8 is gated) |

Gates, fixed before the run. O is the share of the 399 pages with body recall below 0.5.

| Gate | Rule |
| --- | --- |
| G1 | 0 of 129 non-Latin pages kept |
| G2 | kept pages with recall below 0.5 are at most 0.05 of kept pages, without `io06` (333 pages) |
| G3 | escalated share at most O + 0.05 |

O = 0.5163, so the G3 bound is 0.5663. The C0 values at the 0.8 cut reproduce Experiment 33 (escalation 0.469, kept-below-0.5 0.113, drift under 0.0004).

## Results

| Rule | Escalated | Kept bad (no io06) | Kept bad (with io06) | Non-Latin kept | G1 | G2 | G3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 0.469 | 0.106 | 0.113 | 1 of 129 | fail | fail | pass |
| C1 | 0.286 | 0.376 | 0.330 | 19 of 129 | fail | fail | pass |
| C3 | 0.471 | 0.107 | 0.114 | 1 of 129 | fail | fail | pass |
| C0@0.5 | 0.015 | 0.573 | 0.509 | 124 of 129 | fail | fail | pass |
| C0@0.6 | 0.160 | 0.481 | 0.424 | 71 of 129 | fail | fail | pass |
| C0@0.7 | 0.381 | 0.231 | 0.219 | 9 of 129 | fail | fail | pass |
| C0@0.8 | 0.469 | 0.106 | 0.113 | 1 of 129 | fail | fail | pass |
| C0@0.9 | 0.596 | 0.026 | 0.025 | 0 of 129 | pass | pass | fail |

Pages escalated per document (gated pages in brackets), C0 / C1 / C3:

| Document | Script | Pages | C0 | C1 | C3 |
| --- | --- | --- | --- | --- | --- |
| `io01` | Devanagari | 48 | 48 | 45 | 48 |
| `io02` | Arabic | 16 | 15 | 4 | 15 |
| `io03` | Arabic | 5 | 5 | 1 | 5 |
| `io07` | Bengali | 60 | 60 | 60 | 60 |
| `rf06` | Latin handwriting | 43 | 27 | 0 | 27 |
| `rf07` | Latin handwriting | 17 | 11 | 0 | 11 |
| `io06` | Latin early-modern book | 66 | 5 | 2 | 5 |

Other documents (modern print, mixed, text-layer scans) escalate 0 to 12 pages each. The full table is in `output/summary.json`.

### Why G2 fails

C0 keeps 24 bad pages at the 0.8 cut: `rf06` 10, `io06` 8, `rf07` 2, `io04` 2, `io02` 1, `io08` 1. Latin handwriting (`rf06`, `rf07`) supplies 12 of the 16 bad pages outside `io06`. A script rule cannot see handwriting, because the output is Latin. Only the confidence cut moves G2, and only the 0.9 cut gets under 0.05.

### The `io06` finding

13 of the 66 `io06` pages have recall below 0.5. C0 escalates 5 of them (0.385). C1 escalates 2 (0.154). C3 escalates 5. No candidate escalates a majority, and the confidence of the 8 kept bad pages is 0.822 to 0.909. The model is confident and wrong.

C4 tested two signals the rows already hold, as separators of these 13 pages from 143 modern-print pages (recall 0.8 or more):

| Signal | AUC (one-sided) | Follow-up (0.8 or more) |
| --- | --- | --- |
| Discarded-region count | 0.580 | no |
| Characters per page (low is positive) | 0.788 | no |

Characters per page falls 0.012 short of the trigger. With 13 positives the AUC has wide uncertainty, and no bootstrap interval was planned, so this result does not justify a follow-up on its own.

A rule for `io06` needs engine output the rows do not hold: a per-line or per-character confidence spread. That needs a new local OCR run and operator approval.

### Figure-only diagnostic (65 pages)

Escalated share: C0 0.508, C1 0.108, C3 0.554, C0@0.9 0.646. Rules that escalate more on this population waste worker calls on pages whose body text is usable.

## Where the plan was wrong

- **The stray-CJK rate.** The plan set the C1 threshold from a pooled per-document rate (about 0.0001 in Latin documents). Per page the rate is not flat. `tl02` p33 has a CJK share of 0.079 and body recall 0.80. `tl03` p15 has 0.097 and recall 0.88. C1 escalates both. C0 already escalated `tl03` p15, so `tl02` p33 is the one wasted worker call. The 0.05 threshold stays as fixed, and a post-hoc change would break the pre-registration.
- **"Local recall 0.000 on every non-Latin page" (G1 reason).** The median is 0.000 and 103 of 129 pages are exactly 0.000. The other 26 have small positive recall, up to 0.298 (`io01` p49). None reaches 0.5. `io02` p13, the page C0 keeps, has 0.0315. G1 stands, because every one of these pages is unreadable.
- **C1 and Arabic.** The plan listed this limit in the risks. The data confirms it: C1 escalates 5 of 21 Arabic pages.
- **ADR-069 line 115** says "below 0.8". The calibration table supports "below 0.5", which is 0.113 at the 0.8 cut. The correction belongs to a separate documentation change.

## Decisions for the operator

1. Keep the ADR-069 post-check (C0, cut 0.8). This experiment gives no rule that beats it inside the G3 budget.
2. For non-Latin pages, rely on Experiment 37 (`E-script`), which scores the dots.mocr and PaddleOCR-VL workers on the same pages. C0 already escalates 128 of 129.
3. Decide whether to accept the 0.9 cut. It keeps 0 non-Latin pages and 0.026 bad pages. It escalates 238 pages against 187 for C0, which is 51 more worker calls (about 33 minutes at 38.2 s per page) per 399 pages. It fails G3: 238 pages escalated against a bound of 225.
4. For `io06`, a rule needs per-line or per-character confidence. Open a new protocol, with operator approval, if the early-modern book case matters.

## Limits

- One local model, one corpus. The corpus holds no CJK document, so C1 is untested on real CJK text.
- 13 `io06` bad pages. The C4 AUCs have wide uncertainty.
- All recall values are the frozen body recall of Experiment 33. The 2 rows with no body recall are outside the gated population.
- The run read saved texts and ran `freeze.py --check` in the `v3` worktree (decision DR2). The rows file hash matches `plan.json`.

## Reproduce

```bash
E33=<path to the Experiment 33 directory that holds the saved texts>
uv run python experiments/39-local-tier-escalation-2026-09-30/score_rules.py --e33-dir "$E33"
uv run python experiments/39-local-tier-escalation-2026-09-30/summarise_eval.py
uv run python experiments/39-local-tier-escalation-2026-09-30/analysis.py
```

`summarise_eval.py` stops with no summary if the C0 values at 0.8 do not reproduce Experiment 33.
