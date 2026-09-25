# Tasks: Modular OCR workers, with dots.mocr as the primary engine

**Start gate:** start after `page-level-ocr-routing` archives (its `pdf-reader` delta is this change's baseline) and after Experiment 34 closes. Branch: `feat/modular-ocr-workers-dots-mocr`.

**Evidence rule (operator decision 2026-09-24):** Experiment 34 is enough to take the engine and routing decisions. Section 7 is an acceptance check of the built system. It does not gate the decisions.

## 0. Baseline

- [ ] 0.1 After `page-level-ocr-routing` archives, rebase this change's `pdf-reader` delta on the archived spec. Re-copy the routing requirement if its archived text differs. Add a MODIFIED block for "Page-level OCR routing SHALL OCR only pages that need it", so that escalated pages go to "the OCR routes" instead of "the PaddleOCR-VL worker". Verify: `openspec validate modular-ocr-workers-dots-mocr --strict` passes, and `grep -n "PaddleOCR-VL worker" openspec/changes/modular-ocr-workers-dots-mocr/specs/pdf-reader/spec.md` finds nothing.

## 1. Worker core and layout

- [ ] 1.1 Move `ocr-worker/` to `ocr-workers/engines/paddleocr-vl/` with `git mv`, keeping history. Verify: `git log --follow ocr-workers/engines/paddleocr-vl/src/omrg_ocr_paddleocr_vl/engine.py` reaches the old `worker.py` commits.
- [ ] 1.2 Extract `ocr-workers/core/` (package `omrg-ocr-worker-core`): protocol, validation, framing loop, capability command with `backend_id`, page-subset writing and the `OcrEngine` contract (design D1, D2). Verify: the core's unit tests pass in a Paddle-free, PyTorch-free environment.
- [ ] 1.3 Add entry-point loading: exactly one `omrg.ocr_engine` entry point, or the probe reports unavailable. Verify: tests with zero, one and two registered engines match the "An environment with two engines is unavailable" scenario.
- [ ] 1.4 Move the host–worker protocol byte-identity test to the core path. Verify: the test fails when one copy changes by one byte.
- [ ] 1.5 Rewrite `ocr-workers/provision.py <engine>` (design D9) with `--python`, `--dry-run` and `--accept-model-licence`. Verify: `tests/test_ocr_worker_provision.py`, updated, passes; dots-mocr without the flag stops before `uv sync`.
- [ ] 1.6 Add `OMRG_OCR_MODEL_CACHE` handling in the core (design D8). Verify: a test shows engine `x` resolves `$OMRG_OCR_MODEL_CACHE/x/`, and that the engine folder's `.model-cache/` is used when the variable is unset.
- [ ] 1.7 Write `ocr-workers/README.md` with the add-an-engine checklist, and remove the stale "Wave status" text. Verify: the checklist names every file a new engine needs, and it matches the stub engine used in 1.3.

## 2. PaddleOCR-VL engine (fallback)

- [ ] 2.1 Port `worker.py` to `engines/paddleocr-vl/src/omrg_ocr_paddleocr_vl/engine.py` on the core contract. Its output does not change. Verify: the existing smoke test passes on `bd03` p1–p2, and the per-page Markdown equals `experiments/34-worker-sample-review-2026-09-19/output/worker/bd03/` byte for byte.
- [ ] 2.2 Relock (`uv lock`) with the core path dependency. Verify: `python3 ocr-workers/provision.py paddleocr-vl` succeeds on Python 3.11, 3.12 and 3.13, and `--capabilities` reports protocol 1.1 and `backend_id` `paddleocr_vl`.

## 3. dots-mocr engine (primary)

- [ ] 3.1 Create `engines/dots-mocr/` with `pyproject.toml` (licence gate fields), `uv.lock`, and `LICENCE-NOTES.md` recording clauses 3.3(c), 5.2, 8 and 9 of the dots.mocr agreement. Verify: `provision.py dots-mocr --dry-run --accept-model-licence` resolves.
- [ ] 3.2 Implement `omrg-ocr-fetch`: download revision `e539fbb52280393adc081b289ec597430a0f9031`, apply the two patches with line-anchored, idempotent matching, and record code-file hashes (design D4). Verify: running fetch twice leaves identical files and hashes. A test on a copied `modeling_dots_vision.py` shows the second patch run makes no change.
- [ ] 3.3 Implement `layout.py` from the Experiment 34 probe converter, with one `$$` pair per formula, dropped page headers and footers, and `""` for token-cap or unparsable pages. Verify: unit tests on the committed `output/dots_mocr/*/p*.raw.txt` fixtures: `eq01` p11 has exactly 4 display blocks and no `$$` doubling, and `bd03` p2 has no "PLOS One" header or DOI footer line.
- [ ] 3.4 Implement `engine.py`: offline environment variables, hash check at load, MPS-or-CPU device, 200 DPI rendering with a 1600 px minimum long side, and greedy decoding. Verify: with network access blocked, the smoke test on `eq01` p11 returns Markdown whose formulas all render in KaTeX 0.16.22 with no error, and `io06` p28 returns non-empty text.
- [ ] 3.5 Record dots-mocr smoke evidence (seconds per page, MPS memory, packages) in `engines/dots-mocr/SMOKE_RESULTS.md`. Verify: the file is committed with the capability JSON.

## 4. Host routes and settings

- [ ] 4.1 Add the six settings to `config/` and `EffectiveSettings` (design D3), and add them to `.env.example`. Verify: settings tests cover defaults (`dots-mocr` primary, `paddleocr-vl` fallback), env parsing, an empty fallback, and `ocr_maths_page_fraction` bounds 0.0–1.0.
- [ ] 4.2 Implement `integrations/ocr_worker/routes.py`: command resolution, the explicit-command override for the primary route, a shared client for an identical fallback, and `OcrRoutes.select()`. Verify: tests for the "fallback does not start", "explicit command overrides the primary route", "missing primary hands the request to the fallback" and "unknown engine name degrades" scenarios; `uv run lint-imports` passes.
- [ ] 4.3 Scale the request timeout by page count. Verify: the "A long request gets a longer timeout" scenario test passes (14 pages → 1,680 s).
- [ ] 4.4 Wire `build_route_clients` through `capabilities.py` and `compose.py`, with engine- and operation-owned lifecycles as today. Log the resolved primary and fallback engines once at start-up. Verify: `tests/test_ocr_worker_managed.py` and engine shutdown tests pass with two routes.
- [ ] 4.5 Replace the single client in `OcrRoutedPdfInspector` with `OcrRoutes` at every dispatch site. Stamp `ocr_backend` from the answering fingerprint's `backend_id`. Verify: the "Every OCR dispatch…" and "OCR diagnostics SHALL name the answering engine" scenarios pass, including "Post-dispatch failure does not retry on the fallback".

## 5. Maths-page detection and routing

- [ ] 5.1 Implement `integrations/pdf/maths_pages.py` (design D5). Verify: tests for the five detection scenarios. Fixtures:
  - `eq01` p11 (CMEX10, CMMI7/10, CMMIB7/10, CMSY10): flagged;
  - `eq01` p1 (Nimbus and Times only): not flagged;
  - a synthetic CMMI10 font with `/ToUnicode`: flagged;
  - a synthetic Cambria Math page: flagged;
  - a CMR-only page: not flagged;
  - a malformed resource dictionary: nothing flagged.

  A version-pin test covers the pattern tuple.
- [ ] 5.2 Implement `integrations/pdf/maths_routing.py` (design D6) and call it from `OcrRoutedPdfInspector`. Verify: tests for every scenario in `specs/maths-page-routing/spec.md` under "Maths pages SHALL route to the OCR routes", with stub clients. `tests/test_file_size_ceiling.py` passes.
- [ ] 5.3 Emit `pages_maths_font` and add it to `EXCLUDED_EMBED_METADATA_KEYS`. Verify: the diagnostics scenarios pass, and an embedding-text test shows the key absent.

## 6. Identity

- [ ] 6.1 Add `ocr_fallback_fingerprint` and the `maths_routing` block in `core/ingestion/ocr_identity.py`, and advance `_INDEX_IDENTITY_SCHEMA` by one. Coordinate with `normalise-reader-markdown` so both share one bump if they ship together (design D7). Verify: the identity scenarios in `pdf-reader` and `maths-page-routing` pass, and `uv run pytest -m "not slow"` passes.

## 7. Acceptance check on real documents (Experiment 37)

- [ ] 7.1 Create `experiments/37-dots-mocr-routing-acceptance-<date>/` with the s-experiment skill. Verify: `protocol.md` is committed before the run. The corpus has three sets, with PDFs in gitignored `corpus/`, sources in `sources.json`, and page labels made from the page images:
  - **Maths positives:** at least 5 arXiv maths-heavy papers from different fields and years, including one pdfLaTeX paper built with `glyphtounicode` (a Unicode-mapped maths font) and one Word paper with Cambria Math equations.
  - **Negative controls:** the Experiment 34 born-digital documents `bd01`, `bd02` and `bd03`, and one prose-only LaTeX paper.
  - **Scanned set:** the Experiment 34 scanned and problem pages (`io04`, `io06`, `tl03`).
- [ ] 7.2 Run the built system end to end, and report:
  - detection precision and recall per page, the flagged share per paper, and every font name on labelled maths pages that the list does not match;
  - dots-mocr and PaddleOCR-VL on the same maths and scanned pages: seconds per page, the KaTeX error rate over emitted formulas, and every page where either engine emits text absent from the page image (noise or invented text).

  Verify: `output/summary.json` is committed.
- [ ] 7.3 Acceptance:
  - zero flagged pages on the negative controls;
  - a dots-mocr KaTeX error rate at or below 5 % of formulas;
  - the operator reviews the scanned-set noise list.

  If a detection or converter criterion fails, fix it, bump its version, and repeat 7.2. Verify: the verdict and the operator's scanned-set review are recorded in the experiment report and linked from this change.

## 8. Documentation and close

- [ ] 8.1 Update `docs/guides/configuration.md`, `docs/guides/ingestion.md` and `docs/guides/architecture.md`: routes, maths routing, engine folders, the memory note, and the `OCR_WORKER_COMMAND` migration note. Verify: `grep -rn "ocr-worker/" docs` finds no stale path.
- [ ] 8.2 Write the ADR for modular OCR engines, dots.mocr as primary and maths routing with the s-adr skill. It cites Experiment 34 (A2, A4) and Experiment 37, and records the licence terms and the operator's PyTorch approval. Verify: the ADR is committed and indexed.
- [ ] 8.3 Run the gates: `uv sync`, `uv run pytest -m "not slow" --cov=omrg` (core ≥95 %, MCP ≥95 %), `openspec validate --all --strict`, `./scripts/local_ci.sh`. Verify: all pass locally.
- [ ] 8.4 Commit with a `feat(ocr):` message whose body names the one-off reprocessing (identity schema +1), the new primary engine and the moved worker folder. Ask the operator before pushing or opening the PR. Verify: the operator confirms.
