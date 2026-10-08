# Experiment 38: FAIL, no signal passes all gates; Jev and local OpenJev come closest

- **ID**: `38-rescue-quality-signal-2026-09-30`
- **Date run**: 2026-10-07 (pilot run, then rerun under amendment A3 on the same day)
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Pi (pilot) and Claude Code (A3 rerun)
- **Verdict**: FAIL. At held-out thresholds no candidate passes G1, G2 and G3. Hosted Jev and local OpenJev both pass G1 and G2 and flag 12 to 14 healthy pages against an allowance of 11. Production stays unchanged.
- **Protocol**: [protocol.md](protocol.md), [plan.json](plan.json) (amendment A3, wordings, candidates B2 and D)
- **Raw results**: [lodo_summary.json](output/lodo_summary.json) (A3 verdict), [summary.json](output/summary.json) (pilot), [jev_summary.json](output/jev_summary.json), [local_text_signal.json](output/local_text_signal.json)

## Names used in this report

| Label | Plain name | What it is |
| --- | --- | --- |
| A | Word check | Counts real words (`wordfreq` lexicon) and checks the text uses one alphabet. Local, instant. |
| B | Julia 1 | Small local AI model (SupersonicLabs Julia 1, ONNX), whole page. |
| B2 | Julia 1, page head | Julia 1 on the first 2,000 characters, the same input Jev gets. |
| C | Jev | TypeSafe's hosted AI model. Page text leaves the machine. |
| E | OpenJev | Loop AI's open copy of Jev, 27B, MLX 4-bit, run locally. |
| D | Word check then Jev | Word check screens every page; Jev scores only the doubtful ones. |
| D_julia, D_openjev | Word check then Julia 1, or then OpenJev | Same cascade with a different second model. |
| `_sel` suffix | Best wording | The question wording is chosen per document from the other documents. |
| W1 | Original question | "Is this text readable writing in a natural language, rather than garbled or broken OCR output?" |
| W2 | Question with descriptions | "Is this OCR text usable as the real content of the page?" plus yes and no descriptions. |
| W3 | Statement form | "This page text is mostly real words in a natural language, with only minor OCR errors." |

## Bottom line

- Local OpenJev 27B (MLX 4-bit, page text stays on the machine) ranks junk best: AUC 0.956 with W3. It catches 69 of 89 junk pages with W1 and routes no usable document, but flags 14 healthy pages, so it fails G3.
- Hosted Jev is the other useful signal. It ranks junk below healthy pages with AUC 0.878 to 0.922 and catches 56 to 60 of 89 junk pages without routing a usable document.
- It fails because of one gate by one page. With the best wording, it flags 12 of 565 healthy pages (2.12%) against a 2% ceiling (11 pages).
- Julia 1 cannot do this task. Its AUC stays between 0.48 and 0.54 across three wordings and two input lengths. That is random ordering.
- A (word check) catches 37 of 89 junk pages but newly routes usable `rf05` and flags 18 healthy pages.
- The A-then-Jev cascade sends 28% of pages to Jev and catches 50 junk pages. It fails G2 on `rf04`.
- The pilot numbers below the A3 section used a threshold chosen on the test pages. The A3 section replaces them for the verdict.

## Rerun under amendment A3 (verdict)

Amendment A3 (operator, 2026-10-07) changed three things before the rerun. Hosted Jev became registered candidate C. Every equal-cost threshold now uses leave-one-document-out: each document is flagged with a threshold chosen only on the other documents' healthy LiteParse pages. Three question wordings were registered before scoring, and both models pick one per document by nested leave-one-document-out.

### Held-out results (LiteParse tier, gates as frozen)

| Candidate | What it is | Junk flagged | Healthy flagged | G1 | G2 | G3 | Δ vs A | McNemar p |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: |
| A (word check) | `wordfreq` + script checks | 37/89 | 18/565 | PASS | FAIL (`rf05`) | FAIL | | |
| B (Julia 1) | Julia, whole page, W1 | 0/89 | 14/565 | FAIL | PASS | FAIL | −0.416 | 1.0 |
| B2 (Julia 1, page head) | Julia, first 2,000 characters, W1 | 0/89 | 12/565 | FAIL | PASS | FAIL | −0.416 | 1.0 |
| B_sel (Julia 1, best wording) | Julia, wording chosen per document | 2/89 | 12/565 | FAIL | FAIL (`rf04`) | FAIL | −0.393 | 1.0 |
| C (Jev) | Jev, first 2,000 characters, W1 | 60/89 | 14/565 | PASS | PASS | FAIL | +0.258 | 0.00006 |
| **C_sel** | **Jev, wording chosen per document** | **56/89** | **12/565** | PASS | PASS | FAIL | +0.213 | 0.0004 |
| E (OpenJev) | OpenJev 27B local, first 2,000 characters, W1 | 69/89 | 14/565 | PASS | PASS | FAIL | +0.360 | 2e-10 |
| E_sel (OpenJev, best wording) | OpenJev, wording chosen per document | 68/89 | 12/565 | PASS | FAIL (`tl06`) | FAIL | +0.348 | 5e-10 |
| D (word check then Jev) | Cascade: A screens 20%, Jev confirms | 50/89 | 11/565 | PASS | FAIL (`rf04`) | PASS | +0.146 | 0.005 |
| D_julia (word check then Julia 1) | Cascade: A screens 20%, Julia confirms | 16/89 | 10/565 | FAIL | FAIL | PASS | | |
| D_openjev (word check then OpenJev) | Cascade: A screens 20%, OpenJev confirms | 59/89 | 11/565 | PASS | FAIL (`rf05`) | PASS | +0.247 | 2e-07 |

- "Healthy flagged" uses the frozen 2% ceiling: 11 of 565 pages. C_sel's 12 false positives sit in `bd07` (5), `tl03` (4), `tl02` (2) and `tl04` (1).
- Nested selection chose W3 for Julia in all 32 documents with eligible pages. Jev chose W3 in 31 and W2 in 1.
- The 95% document-cluster interval for junk recall is wide for every signal: C 0.048 to 0.882, C_sel 0.048 to 0.808, D 0.000 to 0.822. Junk is concentrated in `rf06` (41 of 89 LiteParse junk pages).
- On the pypdf tier, C flags 60 junk and 4 healthy pages; C_sel flags 50 junk and 11 healthy pages.

### Ranking quality per wording (AUC, junk scored below healthy)

| Model | W1 (original question) | W2 (question with descriptions) | W3 (statement form) |
| --- | ---: | ---: | ---: |
| B (Julia 1), LiteParse | 0.498 | 0.482 | 0.543 |
| B (Julia 1), pypdf | 0.408 | 0.546 | 0.497 |
| C (Jev), LiteParse | 0.878 | 0.913 | 0.922 |
| C (Jev), pypdf | 0.827 | 0.899 | 0.890 |
| E (OpenJev), LiteParse | 0.878 | 0.902 | **0.956** |
| E (OpenJev), pypdf | 0.823 | 0.842 | 0.871 |

All Jev calls returned model `jev-1.13.0`. Nested selection chose W3 for OpenJev in all 32 documents. Wordings and the selection rule are in `plan.json` under `wordings`.

### Why Julia fails

- The encoder matches the publisher's `julia/data.py` token for token. A `noul` request differs from the parity-tested `choice` path only by its head text and type id 2. Full `noul` logit parity needs the PyTorch reference, which this experiment does not install.
- The publisher's `inference-policy.json` states `"calibration": null` and "long-context task accuracy not established".
- Input length is not the cause: B (whole page) and B2 (first 2,000 characters) give the same result.
- Wording is not the cause: three wordings all stay near AUC 0.5.

### Cascade D (word check then a model) sensitivity

| Word check (A) screen rate | Junk flagged (Jev / Julia) | Healthy flagged (Jev / Julia) | Gates (Jev / Julia) | Pages sent to model |
| ---: | ---: | ---: | --- | ---: |
| 0.10 | 48 / 35 | 11 / 13 | all pass / fails G1, G3 | 19% |
| **0.20 (registered)** | 50 / 16 | 11 / 10 | fails G2 (`rf04`) / fails G1, G2 | 28% |
| 0.30 | 50 / 3 | 12 / 11 | fails G2, G3 / fails G1 | 38% |

Julia was given the same cascade (candidate D_julia, registered at the operator's request). It never routes `rf06` and `rf07`, so it fails G1 at every rate, and it catches fewer junk pages than A alone. OpenJev as confirmer (candidate D_openjev) catches 54, 59 and 62 junk pages at screen rates 0.10, 0.20 and 0.30, but newly routes usable `rf05` at every rate, so it fails G2. The Jev 0.10 row passes every gate, but it is a sensitivity setting. Promoting it after seeing the result would be selecting on the test data.

### Local OpenJev setup and cost

- Model: `openjev/openjev-MLX-4bit` (Loop AI, CC BY-NC 4.0, research use). Weights and tokeniser matched the published `SHA256SUMS`; only `README.md` differed.
- Runtime: the publisher's `helper/shim.py` (sha `81a22f1b`) and `shim_mlx.py` at revision `1c341f65`, mlx 0.32.2, mlx-lm 0.31.3, Python 3.12, isolated venv, no PyTorch. Server bound to `127.0.0.1`, Hugging Face offline mode on.
- Speed on this Mac: 6.2 to 7.5 seconds per page, one request at a time. All three wordings took about 7.5 hours.
- Page text never left the machine.

### Cost of hosted Jev

- Page text (first 2,000 characters, including personal records) leaves the machine for every scored page.
- The A3 rerun sent 3,966 requests (1,322 for W1, 2,644 for W2 and W3) and about 2.85 million input tokens. Mean latency was 0.28 s per request.
- Jev has closed weights, and `jev-latest` is an alias that can change model.

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
| A (word check) | As designed | 0.50 | 5/89 (5.62%) | 0/565 (0%) | FAIL | PASS | PASS |
| A (word check) | Equal cost | 0.8834080717 | 37/89 (41.57%) | 11/565 (1.95%) | PASS | FAIL | PASS |
| B (Julia 1) | As designed | 0.50 | 65/89 (73.03%) | 356/565 (63.01%) | PASS | FAIL | FAIL |
| B (Julia 1) | Equal cost | 0.0030147846 | 0/89 (0%) | 11/565 (1.95%) | FAIL | PASS | PASS |

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
| A (word check) | 0.897291 | 0.876633 | 202/206 | 65/193 |
| B (Julia 1) | 0.575406 | 0.445573 | 0/206 | 2/193 |

Candidate A exceeds the baseline by 0.109291 AUC and reaches the 0.8 follow-up trigger. Its fixed threshold is unsuitable for direct local-tier use:

| Signal | Document | Bad pages flagged | Good pages flagged | AUC |
| --- | --- | ---: | ---: | ---: |
| A (word check) | `io06` | 13/13 | 52/53 | 0.876633 |
| A (word check) | `rf06` | 36/36 | 6/7 | 0.876984 |
| A (word check) | `rf07` | 10/12 | 3/5 | 0.783333 |
| B (Julia 1) | `io06` | 0/13 | 0/53 | 0.445573 |
| B (Julia 1) | `rf06` | 0/36 | 0/7 | 0.273810 |
| B (Julia 1) | `rf07` | 0/12 | 0/5 | 0.450000 |

A catches every bad `io06` and `rf06` page at this threshold, and 10 of 12 bad `rf07` pages. It also flags nearly every good `io06` page. Julia catches none of their bad pages at its frozen threshold. A's ranking warrants a separate protocol for local OCR, with that tier's own gates and new threshold validation. This experiment does not set a production threshold.

## Pilot hosted Jev arm (superseded)

The first Jev scoring used one threshold chosen on the test pages (0.28) and passed G1 to G3 with 60/89 junk and 10/565 healthy pages. Leave-one-document-out thresholds (above) replace this result. Raw pilot output: [jev_summary.json](output/jev_summary.json).

## Limits and next actions

1. The A3 rerun is not blind. The pilot had already shown Jev ahead on the same 40 documents, and A3 was written after that.
2. `rf06` holds 41 of 89 LiteParse junk pages, so every junk-recall interval is wide.
3. The 2% ceiling allows 11 healthy pages; C_sel flags 12. One page decides the verdict. More healthy documents would give a stabler rate.
4. `wordfreq` has no Latin-language lexicon. This limits A on `io06`.
5. Julia `noul` logit parity is unverified. The structural check rules out an encoder bug but not a model-side difference.
6. Saved local OCR markdown has a different text distribution from reader-rescue text. The local follow-up was not rerun with Jev wordings.

No production change. Next steps for the operator:

1. Decide whether page text may go to TypeSafe in production. Without that approval, Jev cannot be adopted on any result.
2. If yes, test Jev W3 on new documents with more healthy pages, using the same held-out rules and gates.
3. Drop Julia 1 from further rescue-quality work.
4. Consider local OpenJev as the privacy-safe option. It needs a commercial licence for production and is about 25 times slower than hosted Jev on this Mac. The smaller OpenJev Flash 9B (5 GB) is untested here.

## Validation and workflow status

- Full fast suite: 3,307 passed, 140 skipped, 19 deselected, overall coverage 93%.
- Experiment tests: 80 passed (82 including the documentation link checks). New tests failed before implementation; the A2 drift test also failed with its guard removed.
- All eight import-linter contracts kept; strict OpenSpec validation passed.
- Models, page text and logs stay in gitignored local folders. Frozen Experiment 33 files and production settings/indexes were not changed.
- Main verdict, follow-up, runners, analysis and index are committed at `10012ac`. Six exact Gitleaks exceptions were approved on 2026-10-07; all enabled commit hooks passed.
- NiftyPM AIE-99 was updated, completed and read back on 2026-10-07 (`completed_on=2026-10-07T19:14:20.593Z`). Its description links report file `f!trntW8Rm`, attached to the task and downloaded with an exact SHA-256 match to the committed `d7c9145` report snapshot (10,985 bytes).
- The local `niftypm/omrg.json` completion and description match the verified cloud task. MCP automatic sync emptied the cache arrays; the preserved v3 snapshot was restored and only AIE-99 was refreshed. Other cached records and the full-project `last_synced` timestamp were preserved.
- The native Nifty document read still returns 403; that unused document is not the report reference. The verified file attachment fulfils task 7.2.
- The OpenSpec change is archived at [2026-10-07-experiment-38-rescue-quality-signal](../../openspec/changes/archive/2026-10-07-experiment-38-rescue-quality-signal/), with its six requirements synced to the baseline. The Experiment 39 change was not merged or cherry-picked. Models, page text and the worktree are retained. No Experiment 38 branch push was performed.

## Reproduce

Set `EXP33_SOURCE` to the frozen Experiment 33 directory. Pass it with `--source-exp "$EXP33_SOURCE"` to extraction, classification, candidate scoring, summary and local-text scoring. Use `uv run --locked --with wordfreq==3.1.1` for A and the local follow-up; use `--resume` to reuse complete documents. Julia's pinned download runner and P0 runner are `download_julia.py` and `julia_onnx.py`.

Saved metadata: [rescue_text.json](output/rescue_text.json), [candidate_a.json](output/candidate_a.json), [candidate_b.json](output/candidate_b.json), [parity.json](output/parity.json), [summary.json](output/summary.json), [local_text_signal.json](output/local_text_signal.json). [analysis.py](analysis.py) loads these results without running experiments.

## OpenSpec verification (2026-10-07)

| Dimension | Evidence and status |
| --- | --- |
| Completeness | 16/16 tasks checked. Six added requirements mapped. Task 6.1's summary is committed; task 7.2's cloud and local state were verified. |
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

**Workflow verification:** all 16 tasks are complete and the change is archived. The report attachment was verified byte-for-byte, AIE-99's completion was read back, and the local mirror agrees. Final fast tests, targeted checks and strict spec validation passed. The native-document read and automatic-cache-sync issues are outside this experiment; the supported file attachment and restored snapshot resolved its workflow requirements.
