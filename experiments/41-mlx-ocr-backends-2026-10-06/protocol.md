# Experiment 41: MLX OCR backends for dots.mocr and PaddleOCR-VL

- **ID**: `41-mlx-ocr-backends-2026-10-06`
- **Date planned**: 2026-10-06
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, Claude Code (plan)
- **Status**: PLANNED (no install, download or OCR run is approved; see `plan.json`, `approvals`)
- **Relation**: OpenSpec change `experiment-41-mlx-ocr-backends`; Experiment 37 findings F4 and F5; Experiment 34 (A2, A4); ADR-072
- **Plan**: [`plan.json`](plan.json) (arms, page lists, candidate gates, approvals, open decisions)
- **Number**: 41. Number 40 is reserved in NiftyPM for AIE-101, "page versus document OCR routing on mixed PDFs".

## Why this experiment exists

Experiment 37 accepted dots.mocr as the primary OCR engine and left two costs open.

1. PaddleOCR-VL on CPU timed out on 34 of 257 pages at 300 s and needed 35 worker restarts (F4).
2. dots.mocr peaked at 22.2 GiB of memory on PyTorch MPS (F5).

Apple's MLX framework may cut both costs. A two-page test on 2026-10-05 ran PaddleOCR-VL on MLX in 6.6 s and 9.4 s, against 87 s and 133 s on CPU. That test was a scratch session. Its environment is gone. It covered two pages of one paper, so it cannot support a decision.

This experiment asks one decision question: **can an MLX backend replace the current backend for each engine, without losing output quality?** A pass leads to a separate OpenSpec change for an MLX engine folder. This experiment changes no engine, route or default.

## Questions

Gates are not fixed here. The operator sets them in `plan.json` (`gates`) before any run. Section "Candidate gates" lists proposals.

1. **Q1 Speed.** How many seconds per page does each MLX arm need, against its baseline arm?
2. **Q2 Memory.** What peak memory does each MLX arm reach, server process included?
3. **Q3 Reliability.** How many pages time out or return empty text?
4. **Q4 Formulas.** What share of emitted formulas fail to render in KaTeX 0.16.22, and which formulas change against the baseline? The scratch test showed `\p\theta`, `\pmb{0}` and one dropped `$$`.
5. **Q5 Scripts.** Does token recall on the 189 script and handwriting pages hold?
6. **Q6 Invented text.** Does an MLX arm invent text that is absent from the page image?
7. **Q7 Similarity.** How close is each MLX output to its baseline output, page by page?

## Background and prior evidence

- Experiment 37 report: `experiments/37-dots-mocr-routing-acceptance-2026-09-30/report.md`. Per-page Markdown and states are the baseline.
- Experiment 34: probe pattern (a standalone script in its own environment, with the operator reviewing pages).
- PaddleOCR documents `vl_rec_backend="mlx-vlm-server"` for Apple Silicon. It needs `mlx-vlm` 0.3.11 or later and a running `mlx_vlm.server`. The server exposes an OpenAI-compatible API. Source: PaddleOCR `PaddleOCR-VL-Apple-Silicon` guide, read 2026-10-06.
- `mlx-vlm` supports `dots_ocr` (dots.ocr and dots.mocr) and `paddleocr_vl` model types. Source: DeepWiki for Blaizzy/mlx-vlm, read 2026-10-06. The first version that added each is not recorded there. The experiment records the installed version.
- MLX conversions on the Hub (checked 2026-10-06): `mlx-community/dots.mocr-bf16` (base `rednote-hilab/dots.mocr`, the same organisation as our pinned model) and `mlx-community/dots.mocr-{4,5,6,8}bit`, `-mxfp4`, `-mxfp8`, `-nvfp4` (base `dots-studio/dots.mocr`). The quantised cards carry the tag `license:mit`. The agreement we accepted has extra clauses (3.3(c), 5.2, 8, 9) and covers derivative works.
- PaddleOCR-VL needs no third-party conversion in the plan. The official `PaddlePaddle/PaddleOCR-VL-1.6` repository (Apache-2.0) is the weight source, loaded by `mlx-vlm` in bf16.

### Two limits of the Experiment 37 baseline

1. **Shared load.** In Experiment 37 the two engines ran at the same time, dots.mocr on the GPU and PaddleOCR-VL on CPU. Only the first 20 dots.mocr pages ran alone. The baseline timings carry some shared load. MLX arms run alone, so part of any speed gain could come from that difference. Open decision DR-1 asks the operator whether to re-time the baselines alone on a subsample.
2. **Different weights.** The MLX bf16 conversions are not byte copies of the PyTorch weights. Output differences come from the backend, the conversion and the numerics together. The experiment cannot separate them.

## Arms

| Arm | Engine | Backend | Source of results |
| --- | --- | --- | --- |
| `A1` | dots.mocr | PyTorch MPS, bf16 (shipped) | reuse Experiment 37 `output/dots-mocr/` |
| `A2` | dots.mocr | MLX, bf16 (`mlx-community/dots.mocr-bf16`) | new run |
| `A3` | PaddleOCR-VL | CPU (shipped) | reuse Experiment 37 `output/paddleocr-vl/` |
| `A4` | PaddleOCR-VL | MLX, bf16 (`vl_rec_backend="mlx-vlm-server"`) | new run |

Comparisons: `A2` against `A1`, and `A4` against `A3`. Cross-engine comparison (`A2` against `A4`) is reported and not gated.

Quantised conversions (8 bit and lower) are out of scope. They belong to a second experiment if bf16 passes and memory is the remaining problem.

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | Backend | PyTorch MPS or CPU (baseline), MLX bf16 (candidate) |
| Dependent | Speed | seconds per page, median and 90th percentile |
| Dependent | Memory | peak physical footprint, client and server process summed |
| Dependent | Reliability | timeouts, empty results, worker or server restarts |
| Dependent | Formula validity | KaTeX 0.16.22 render error rate |
| Dependent | Script recall | token recall on `E-script`, Experiment 33 tokeniser |
| Dependent | Invented text | operator verdict on screened pages |
| Dependent | Similarity | token Dice coefficient against the baseline arm, per page |
| Controlled | Pages | the same 257 pages as Experiment 37, same page lists |
| Controlled | Prompt, render size, token cap, decoding | the dots.mocr engine constants: `prompt_layout_all_en`, 200 DPI with the engine's long-side rule, `MAX_NEW_TOKENS` 8192, greedy decoding |
| Controlled | Post-processing | the engine's `layout.py` (header and footer dropped, one `$$` pair per display formula) applied to the MLX arm output |
| Controlled | Request timeout | 300 s per page |
| Controlled | Machine load | MLX arms run alone, one at a time, with no other GPU job |

Not changed: engine folders, routes, settings defaults, the maths detector, the pinned PyTorch dots.mocr revision `e539fbb52280393adc081b289ec597430a0f9031`.

## Corpus and ground truth

No new documents. Reuse everything from Experiment 37, without relabelling.

| Run | Pages | Ground truth |
| --- | ---: | --- |
| `E-maths` | 40 | maths labels `maths_labels.json` (sha256 `324ef438…`, frozen); KaTeX check only |
| `E-scan` | 28 | operator noise review |
| `E-script` | 189 | Experiment 33 reference transcriptions (split body text) |
| **Total** | **257** | |

Page lists come from Experiment 37 (`output/ocr_state_dots-mocr.json`, key `page_lists`, seed 37). Experiment 41 copies them into `plan.json` and freezes them with a SHA-256.

The Experiment 37 gitignored outputs are preserved in the v3 worktree (2026-10-06, Gotcha #15). This experiment reads them there. The corpus PDFs sit in `corpus/`, with the same layout as Experiment 37, and their SHA-256 values match `sources.json`.

## Environment and prerequisites

| Requirement | Value |
| --- | --- |
| OMRG | `v3` at `80dcf24` or later (modular OCR workers merged) |
| MLX environment | gitignored `mlx-env/` in the experiment folder; `mlx-vlm` pinned at install and recorded; **not installed yet** |
| PaddleOCR-VL engine | `ocr-workers/engines/paddleocr-vl/`, already provisioned (layout model `PP-DocLayoutV3` runs on CPU in `A4` too) |
| dots.mocr engine code | `ocr-workers/engines/dots-mocr/` (constants and `layout.py` read for `A2`; its PyTorch environment is not used) |
| Model cache | `OMRG_OCR_MODEL_CACHE=~/Development/DATA/omrg/ocr-models`, MLX weights in an `mlx/` subfolder |
| Hardware | the operator's Apple Silicon Mac, as in Experiment 37 |
| KaTeX | 0.16.22, installed with Bun in gitignored `katex/` (`bun add katex@0.16.22`) |
| Network | allowed only for the approved downloads; off during runs (`HF_HUB_OFFLINE=1`) |

## Design

| Run ID | Purpose | Arms |
| --- | --- | --- |
| `S-smoke` | two pages (`eq01` p2, p3): confirm the setup before the full run | `A2`, `A4` |
| `E-maths` | Q1 to Q4, Q7 | `A2`, `A4` |
| `E-scan` | Q1 to Q3, Q6, Q7 | `A2`, `A4` |
| `E-script` | Q1 to Q3, Q5, Q7 | `A2`, `A4` |
| `T-control` (if DR-1 says yes) | re-time the baselines alone on a seeded subsample | `A1`, `A3` |

How the arms run:

- `A4`: a standalone script builds `PaddleOCRVL` inside the already provisioned PaddleOCR-VL environment with `vl_rec_backend="mlx-vlm-server"`, pointing at a local `mlx_vlm.server`. The server runs in the separate `mlx-env/`. The script reuses the engine's page-subset handling, so TDR-027 and TDR-029 stay covered. The paths of the PaddleOCR-VL engine do not change.
- `A2`: a standalone script in `mlx-env/` renders each page, calls `mlx-vlm` with the engine prompt, then applies the engine's `layout.py`. Open item OI-1 checks that `layout.py` imports no PyTorch before it is reused.
- Both scripts write each page to `output/<arm>/<doc_id>/p<NNN>.md` atomically (`.tmp`, then rename), keep a state file per arm, and support `--resume`. They run detached and print with `flush=True`.
- Neither script goes through `OcrRoutes`. No MLX engine folder exists yet. That is the follow-up change if the experiment passes.

## Metrics

### Primary (gated, operator sets the gates)

- Median seconds per page and share of pages with a timeout, per arm.
- KaTeX error rate over `E-maths` and `E-scan`, per arm.
- Median token recall on `E-script`, per arm.
- Operator verdict on every page of the noise list (invented text), per arm.

### Reported (not gated)

- 90th percentile and maximum seconds per page; engine time in hours.
- Peak memory (client and server summed), with the sampling method from Experiment 37 (`proc_pid_rusage` lifetime maximum, applied to both processes).
- Token Dice coefficient against the baseline arm, per page: median, share below 0.9, and the 20 lowest pages.
- Formulas present in the baseline output and altered or missing in the MLX output (a list, not a rate).
- Token recall per writing system (Devanagari 48, Arabic 21, Bengali 60, Latin handwriting 60), beside Experiment 33 local-tier recall.
- Cross-engine comparison `A2` against `A4`.
- First-call cost (load time) per arm, apart from page time.

The scratch test reported "token match 0.947 and 0.962" with no recorded definition. This experiment defines similarity as the Dice coefficient over token multisets (Experiment 33 `build_labels.tokens`, imported). Scratch numbers are context only.

## Candidate gates (the operator sets or replaces these)

| ID | Candidate rule | Why this value |
| --- | --- | --- |
| C1 | `A2` median seconds per page at most 0.5 times `A1` (37.0 s); `A4` at most 0.5 times `A3` (40.2 s) | a 2 times gain is the least that justifies a new engine folder |
| C2 | `A4` has 0 timeouts at 300 s | `A3` had 34 of 257 |
| C3 | KaTeX error rate at most 0.05 for `A2` and for `A4` | the Experiment 37 G2 rule |
| C4 | median `E-script` recall of each MLX arm at least its baseline median minus 0.05 | baselines: `A1` 0.889, `A3` 0.610 |
| C5 | operator finds no invented text on the noise list, as in Experiment 37 G3 | same rule |
| C6 | median Dice similarity to the baseline at least 0.90 | scratch test showed 0.947 and 0.962 on two pages, by an unrecorded method |
| C7 | `A2` peak memory below 22.2 GiB | the F5 figure; reported, gate only if the operator wants it |

Pass rule candidate: C1 to C5 all hold for an arm. C6 and C7 inform the decision.

## Procedure

1. Operator sets the gates and DR-1 in `plan.json`. Freeze `plan.json` (SHA-256 recorded).
2. Operator approves the four gates in `plan.json` (`approvals`): install, downloads, licence check, run budget. Each stays `false` until then.
3. Install `mlx-vlm` into `mlx-env/` and record the version. Install KaTeX.
4. Download the weights into the model cache. Record each repository revision.
5. Run `S-smoke` on `eq01` p2 and p3. Compare with the scratch figures. Stop if the output is empty or the server fails.
6. Run `A4`, then `A2`, each alone, through `E-maths`, `E-scan`, `E-script`.
7. If DR-1 says yes, run `T-control`.
8. Score KaTeX, recall and similarity. Build the review page from the noise list and the lowest-similarity pages. Follow `references/review-page-pattern.md` and the Experiment 34 layout.
9. Operator reviews. Write `report.md`, `output/summary.json` and the verdict. Update `EXP_README.md`.

## Interpretation rules

- A pass on an arm supports a follow-up OpenSpec change for an MLX engine folder. It does not change a default.
- A fail on C3 or C5 for one arm leaves that engine on its current backend. The other arm decides separately.
- If only `A4` passes, the change targets PaddleOCR-VL first. That helps F4, because PaddleOCR-VL is the fallback and the timeout problem.
- A speed gain that disappears under `T-control` is reported as a baseline artefact.
- Differences in formulas are findings. The report lists them even when the gates pass.
- The result applies to this Mac and these 257 pages. It says nothing about other hardware.

## Runtime budget (estimate, operator authorises)

| Run | Pages | `A4` | `A2` |
| --- | ---: | ---: | ---: |
| `E-maths` | 40 | about 4.5 to 6.5 min | about 8 to 25 min |
| `E-scan` | 28 | about 3 to 4.5 min | about 6 to 17 min |
| `E-script` | 189 | about 21 to 30 min | about 35 min to 1.9 h |
| **Total** | **257** | **about 0.5 to 0.7 h** | **about 0.9 h to 2.6 h** |

`A4` rates come from the scratch test (6.6 s and 9.4 s per page, two pages). `A2` has no measurement, so the range runs from a 3 times gain to no gain against the Experiment 37 median of 37.0 s. Add model load (the scratch first call took 211 s, with a 1.8 GB download). Total about 1.5 h to 3.5 h of GPU time for both arms. No cap is set. The operator fills `runtime_budget_h` in `plan.json`.

## Approvals and licence

`plan.json`, `approvals` holds four gates. All are `false`.

1. Install `mlx-vlm` into the gitignored experiment environment.
2. Download model weights: about 1.8 GB for PaddleOCR-VL and about 6 GB for dots.mocr bf16.
3. Licence check. The dots.mocr agreement covers "derivative works" (clause 3.3). An MLX conversion is a derivative. The operator accepted the agreement for the pinned PyTorch model on 2026-10-04. The operator decides whether that acceptance covers `mlx-community/dots.mocr-bf16`, and whether the conversion's stated base (`rednote-hilab/dots.mocr`) and revision are acceptable. PaddleOCR-VL is Apache-2.0 and needs no extra check.
4. OCR run budget and authorisation.

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan; page lists, candidate gates, approvals, open decisions |
| `run_mlx.py` | standalone runner for `A2` and `A4` (to write) |
| `start_mlx.sh`, `stop_mlx.sh`, `status_mlx.py` | detached run helpers, same pattern as Experiment 37 |
| `score_recall.py`, `check_katex.mjs` | thin wrappers over the Experiment 37 scripts with the new arm names |
| `similarity.py` | Dice similarity and formula-difference list (to write) |
| `make_noise_review.py` | review page for the noise list and lowest-similarity pages |
| `output/<arm>/…` | per-page Markdown (gitignored) |
| `output/ocr_state_<arm>.json` | per-page status, seconds, memory (committed only in summary form) |
| `output/pages.json`, `output/summary.json` | per-page rows and gate values (committed) |
| `report.md` | verdict and the operator's review |

## Open items

- **OI-1.** Confirm that `omrg_ocr_dots_mocr/layout.py` imports no PyTorch. If it does, copy its logic by hash-pinned reference.
- **OI-2.** Check that `mlx-vlm` loads `rednote-hilab/dots.mocr` at the pinned revision with `model_type` `dots_ocr`, or decide that the `mlx-community` conversion is the only route.
- **OI-3.** Confirm how the `A4` script reuses the engine's page-subset code (TDR-027) without changing the engine folder.
- **OI-4.** Pick the number of lowest-similarity pages for the review page (candidate: 20 per arm, plus all screened noise pages, plus 10 random pages with seed 41).

## References

- `experiments/37-dots-mocr-routing-acceptance-2026-09-30/report.md`, `plan.json`, `output/ocr_state_*.json`, `run_ocr.py`, `score_recall.py`, `check_katex.mjs`, `make_noise_review.py`
- `experiments/34-worker-sample-review-2026-09-19/` (probe and review layout)
- `experiments/33-ocr-routing-natural-positive-2026-09-17/` (labels, tokeniser, reference transcriptions)
- `docs/adr/072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md`
- `ocr-workers/engines/dots-mocr/LICENCE-NOTES.md`
- PaddleOCR `PaddleOCR-VL-Apple-Silicon` guide (`vl_rec_backend`, `vl_rec_server_url`, `vl_rec_api_model_name`)
