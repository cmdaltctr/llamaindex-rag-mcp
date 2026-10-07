# Experiment 38: FAIL, recommend neither rescue-quality signal

- **ID**: `38-rescue-quality-signal-2026-09-30`
- **Date run**: 2026-10-07
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Pi
- **Verdict**: Neither A nor Julia 1 passes the rescue gates. Production stays unchanged.
- **Protocol**: [protocol.md](protocol.md), [plan.json](plan.json)
- **Raw results**: [summary.json](output/summary.json), [local_text_signal.json](output/local_text_signal.json)

## Bottom line

Candidate A catches junk at the allowed page cost, but its false positives cluster in healthy document `rf05`. Julia's scores reject many healthy pages; at the allowed cost it catches no junk. Candidate A ranks bad local OCR text well in the follow-up. Its rescue threshold sends too many good local OCR pages for another pass.

## Setup and checks

Both rescue tiers were extracted from all 40 frozen Experiment 33 documents: 1,123 pages each. LiteParse 2.11.1 ran with OCR disabled; pypdf 6.16.2 used the shipped adapter. The shipped normaliser was version 2.

| Tier | Junk | Healthy | Grey (not scored) | Excluded |
| --- | ---: | ---: | ---: | ---: |
| LiteParse | 89 | 565 | 38 | 431 |
| pypdf | 89 | 579 | 24 | 431 |

The original size estimates used all-text `r_pypdf`; actual body-only classes differ. Every candidate scored 654 LiteParse and 668 pypdf page/tier pairs.

The operator approved `wordfreq==3.1.1` and the pinned Julia download on 2026-10-07. Amendment A2, committed at `f74abb1` before candidate scoring, checks all-text recall against frozen `r_pypdf` and uses body recall for quality. All 1,123 checks passed; the largest difference was 0.00005 against a 0.0001 limit. The first failed check remains in [recall_check_before_a2.json](output/recall_check_before_a2.json).

Julia used ONNX revision `82a2fadf8fccfccdc5fd4e1009ba8f1a265eb7a8` and ONNX Runtime on CPU, without PyTorch. P0 passed: 100/100 argmax matches, maximum absolute logit error 0.0001037121. The encoder used the published policy, `max_length=8192`, `head_length=512`, strict encoding. All published parity cases are `choice`; none tests `noul`, the yes/no type used here.

## Rescue results

Junk recall is the share of junk pages flagged. Healthy false-positive rate is the share of healthy pages flagged. A page is flagged when its score is strictly below the threshold. Equal-cost thresholds preserve ties; finite counts give 11/565 (1.947%) instead of exactly 2%.

| Signal | Operating point | Threshold | Junk flagged | Healthy flagged | G1: both misses route | G2: no new usable route | G3: ≤2% healthy flags |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| A | As designed | 0.50 | 5/89 (5.62%) | 0/565 (0%) | FAIL | PASS | PASS |
| A | Equal cost | 0.8834080717 | 37/89 (41.57%) | 11/565 (1.95%) | PASS | FAIL | PASS |
| Julia | As designed | 0.50 | 65/89 (73.03%) | 356/565 (63.01%) | PASS | FAIL | FAIL |
| Julia | Equal cost | 0.0030147846 | 0/89 (0%) | 11/565 (1.95%) | FAIL | PASS | PASS |

At equal cost, A flags 25/89 pages of `rf06` and 7/63 of `rf07`. Both reach the unchanged 10% routing fraction. It also flags 3/25 pages of usable `rf05`, which newly routes. Projected wasted OCR: 25 pages, 955 seconds with dots.mocr, or 580 to 4,102.5 seconds with PaddleOCR-VL. Julia flags no rescue page of either motivating miss at equal cost.

Julia's original threshold newly routes nine usable documents: `tl04`, `tl05`, `tl06`, `rf01`, `rf02`, `rf03`, `rf04`, `rf05`, `rf08`. The baseline routes stay in the simulation. The JSON contains all 40 documents at both operating points.

The 95% document-cluster bootstrap intervals for LiteParse junk recall are A: 0.000–0.197 (as designed), 0.048–0.540 (equal cost); Julia: 0.543–0.820 and 0.000–0.000. Each uses 2,000 document resamples, seed 38. Per-document recall is saved in the summary.

Julia's equal-cost recall difference from A is −0.4157303371. Exact one-sided McNemar gives 37 A-only detections, 0 Julia-only detections, p=1.0. The required +0.10 margin and p<0.05 are not met.

Secondary pypdf uses the same LiteParse thresholds. A flags 5/89 junk and 0/579 healthy as designed; at equal cost, 36/89 junk and 15/579 healthy. Julia flags 79/89 junk and 433/579 healthy as designed; at equal cost, 0/89 junk and 45/579 healthy. These diagnostic rates do not determine adoption.

Mean CPU time per scored page/tier: A 0.000633 seconds, Julia 0.333167 seconds. Julia used two CPU threads; mean wall time was 0.167930 seconds. Loading the model is outside the per-page timings.

## Post-verdict local OCR follow-up

Both signals scored all 464 saved texts after `freeze verified`, since the main verdict selected neither. The same signal code, prompt and equal-cost thresholds were reused. No threshold or question was retuned. The primary follow-up population is the 399 pages whose frozen `body_label` is `needs_ocr`; 206 have saved `body_recall` below 0.5.

AUC measures how well lower scores separate bad text from good text: 1.0 is perfect separation, 0.5 is tied/random ranking. Experiment 39's characters-per-page baseline is 0.788; its follow-up trigger is 0.8.

| Signal | AUC, 399 gated pages | AUC, `io06` (66 pages) | Bad flagged, gated | Good flagged, gated |
| --- | ---: | ---: | ---: | ---: |
| A | 0.897291 | 0.876633 | 202/206 | 65/193 |
| Julia | 0.575406 | 0.445573 | 0/206 | 2/193 |

Candidate A exceeds the baseline by 0.109291 AUC and reaches the 0.8 follow-up trigger. Its fixed threshold is unsuitable for direct local-tier use:

| Signal | Document | Bad pages flagged | Good pages flagged | AUC |
| --- | --- | ---: | ---: | ---: |
| A | `io06` | 13/13 | 52/53 | 0.876633 |
| A | `rf06` | 36/36 | 6/7 | 0.876984 |
| A | `rf07` | 10/12 | 3/5 | 0.783333 |
| Julia | `io06` | 0/13 | 0/53 | 0.445573 |
| Julia | `rf06` | 0/36 | 0/7 | 0.273810 |
| Julia | `rf07` | 0/12 | 0/5 | 0.450000 |

A catches every bad `io06` and `rf06` page at this threshold, and 10 of 12 bad `rf07` pages. It also flags nearly every good `io06` page. Julia catches none of their bad pages at its frozen threshold. A's ranking warrants a separate protocol for local OCR, with that tier's own gates and new threshold validation. This experiment does not set a production threshold.

## Limits and next actions

1. Equal-cost thresholds were chosen on these test pages; production needs validation on new documents.
2. `rf06` clusters many junk pages; document resampling gives broad intervals.
3. `wordfreq` has no Latin-language lexicon. This limits A on `io06`; its Latin-script words still use the listed languages.
4. Published parity covers no `noul` requests. The fixed Julia question was not searched or changed.
5. Saved local OCR markdown has a different text distribution from reader-rescue text.

The main recommendation is neither signal. The conditional production proposal in task 7.3 does not apply. Keep TDR-024 and production defaults unchanged. A new local-tier protocol is the next scientific step.

## Validation and workflow status

- Full fast suite: 3,307 passed, 140 skipped, 19 deselected, overall coverage 93%.
- Experiment tests: 80 passed (82 including the documentation link checks). New tests failed before implementation; the A2 drift test also failed with its guard removed.
- All eight import-linter contracts kept; strict OpenSpec validation passed.
- Models, page text and logs stay in gitignored local folders. Frozen Experiment 33 files and production settings/indexes were not changed.
- Main verdict, follow-up, runners, analysis and index are committed at `10012ac`. Six exact Gitleaks exceptions were approved on 2026-10-07; all enabled commit hooks passed.
- NiftyPM AIE-99 remains pending because its MCP tools are unavailable. The cached `niftypm/omrg.json` mirror was restored from v3, with its results description prepared locally; cloud completion stays false and `last_synced` is unchanged.
- Nothing was pushed or archived. The Experiment 39 change was not merged or cherry-picked. Model files are retained locally while workflow completion is blocked.

1. Enable NiftyPM tools before updating and verifying AIE-99 against the restored mirror.
2. Complete task 7.2 only after the cloud task and local mirror agree.

## Reproduce

Set `EXP33_SOURCE` to the frozen Experiment 33 directory. Pass it with `--source-exp "$EXP33_SOURCE"` to extraction, classification, candidate scoring, summary and local-text scoring. Use `uv run --locked --with wordfreq==3.1.1` for A and the local follow-up; use `--resume` to reuse complete documents. Julia's pinned download runner and P0 runner are `download_julia.py` and `julia_onnx.py`.

Saved metadata: [rescue_text.json](output/rescue_text.json), [candidate_a.json](output/candidate_a.json), [candidate_b.json](output/candidate_b.json), [parity.json](output/parity.json), [summary.json](output/summary.json), [local_text_signal.json](output/local_text_signal.json). [analysis.py](analysis.py) loads these results without running experiments.

## OpenSpec verification (2026-10-07)

| Dimension | Evidence and status |
| --- | --- |
| Completeness | 15/16 tasks checked. Six added requirements mapped. Task 6.1's summary is committed; only task 7.2 remains blocked. |
| Correctness | All eight specified scenarios have implementation/test evidence. 80 experiment tests passed; two documentation checks also passed. |
| Coherence | D1 to D7 followed, including approved A2. Frozen thresholds, gates, request and revisions match the original plan at `497204b`. |

| Requirement | Implementation and checks |
| --- | --- |
| Frozen body-based junk classes | `score_candidates.py:41`, `test_labels.py`; all-page all-text sanity check passed. |
| Fixed adoption margin | `summarise_eval.py:15`, `test_summary.py`; original 0.10 margin and exact one-sided paired test preserved. |
| Page/document false-positive cost | `summarise_eval.py:22`, `test_summary.py`; both operating points and all 40 routing rows saved. |
| Motivating misses | `summarise_eval.py:49`, `test_summary.py`; `rf06` and `rf07` evaluated at the unchanged 0.10 fraction. |
| Local inference, no PyTorch | `julia_onnx.py:19`, `test_julia.py`, `test_download.py`, `test_signals.py`; P0 passed and hosted candidate rejected before source access. |
| Unchanged production behaviour | No diff under `src/`, `pyproject.toml` or `uv.lock`; the winning-signal proposal condition is not met. |

All saved summary artefact hashes and 464 local text hashes were verified. Resume completed without rescoring for A, B and the local follow-up. The notebook was generated and is gitignored. Analysis ran with the non-interactive plotting backend; its display warning does not affect the tables or plots created in memory.

**Workflow verification:** task 6.1 is complete with its summary committed at `10012ac`. Task 7.2 requires live NiftyPM access before archive. The restored mirror contains the prepared description and remains explicitly unsynced; its cached completion flag is false.
