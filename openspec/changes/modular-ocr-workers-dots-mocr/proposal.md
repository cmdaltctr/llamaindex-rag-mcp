# Proposal: Modular OCR workers, with dots.mocr as the primary engine

## Why

Born-digital maths papers lose their equations today. On `eq01` p11 (Kingma & Welling, arXiv 1312.6114v11), pdf-inspector dropped all 35 Greek letters and all 8 minus signs, and LiteParse kept the characters but scrambled the equation order (Experiment 34, amendment A4). A maths font's Unicode map does not help: it restores characters, not equation structure. Neither reader flags these pages for OCR, so they never reach a worker. dots.mocr returned every equation as correct LaTeX, with equation tags and bold kept, in 55.7 s against 75.7 s for PaddleOCR-VL.

The worker is also hard-wired to one engine. `ocr-worker/` is one PaddleOCR-VL project, and the host reaches it through one `OCR_WORKER_COMMAND`. OCR models change fast, so a second engine must not mean a second copy of the protocol, framing loop and provisioning code.

Operator decisions of 2026-09-24:

- dots.mocr becomes the primary OCR engine for every OCR route, scanned pages included. PaddleOCR-VL becomes the fallback.
- The Experiment 34 evidence is enough to take the decision, so no gating experiment runs first. A multi-paper acceptance check runs on the built system (tasks, section 7).

## What Changes

- **Modular worker layout.** Replace `ocr-worker/` with `ocr-workers/`:
  - `core/`: one shared worker package. It holds the protocol, validation, the JSON Lines framing loop, the capability command, page-subset writing and the engine contract.
  - `engines/<engine>/`: one isolated project per engine, with its own `pyproject.toml`, `uv.lock` and gitignored model cache. An engine registers itself through one Python entry point.
  - `provision.py <engine>`: one provisioning script for every engine.
  - Adding an engine means adding one engine folder and naming it in a route setting. No host code changes.
- **PaddleOCR-VL moves to `engines/paddleocr-vl/`** and becomes the fallback engine. Its output does not change.
- **New primary engine `engines/dots-mocr/`.** It runs dots.mocr (3 B, PyTorch) from a pinned model revision, offline at parse time. It drops page headers and footers, which dots.mocr labels. The operator approved PyTorch for this isolated environment on 2026-09-24. PyTorch stays out of the OMRG install and off the retrieval path.
- **Two routes, primary then fallback.** Every OCR dispatch uses the primary route: scanned PDFs, gate-selected PDFs, escalated pages and maths pages. If the primary is unavailable before dispatch, the fallback route takes the same request. If neither is available, the existing degraded behaviour applies. A failure after dispatch stays a per-file error, with no retry on the other route.
- **Licence gate.** Provisioning dots.mocr requires `--accept-model-licence`. The engine folder records the licence terms that affect OMRG (see Impact).
- **Maths-page detection.** A new host-side detector flags a born-digital page when it uses a maths font from a closed, versioned list, whether or not the font has a Unicode map. The list covers Computer Modern and Latin Modern maths, AMS symbol fonts, and the common OpenType maths fonts (Cambria Math, STIX, XITS, TeX Gyre maths, Libertinus Math). The detector uses `pypdf`, which is already a core dependency.
- **Maths routing.**
  - Page unit: flagged pages skip the local OCR tier and go to the OCR route.
  - Document unit: the whole PDF goes to the OCR route when the flagged-page fraction reaches the configured threshold.
- **Settings.** New top-level settings:
  - `OCR_WORKERS_DIR`: where the engine folders are.
  - `OCR_ENGINE_PRIMARY`: default `dots-mocr`.
  - `OCR_ENGINE_FALLBACK`: default `paddleocr-vl`; empty means no fallback.
  - `OCR_MATHS_ROUTING_ENABLED`: default `true`.
  - `OCR_MATHS_PAGE_FRACTION`: default `0.10`, used by the document unit.
  - `OCR_WORKER_SECONDS_PER_PAGE`: default `120`.
  - `OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR` stay valid as an explicit override for the primary route.
- **Honest diagnostics.** `ocr_backend` names the engine that produced the text (`dots_mocr`, `paddleocr_vl`, or `mixed`). A new scalar, `pages_maths_font`, counts the flagged pages.
- **Index identity.** The identity gains the fallback route's fingerprint and a `maths_routing` block (enabled, fraction, detector version). The identity schema advances by one. **Reprocessing:** every existing source re-ingests once, as in schemas 4 to 6.

## Capabilities

### New Capabilities

- `ocr-worker-engines`: the modular worker layout, the shared worker core, the engine contract and entry-point registration, per-engine isolated provisioning, the licence gate, the dots-mocr output contract, and the primary and fallback routes.
- `maths-page-routing`: maths-font detection, routing of maths pages in both routing units, the diagnostics and the identity block.

### Modified Capabilities

- `pdf-reader`: four requirements change.
  - The OCR routing requirement names the OCR routes, not PaddleOCR-VL.
  - The isolation requirement covers every engine.
  - The Markdown-convergence requirement covers every engine.
  - The fingerprint identity requirement covers both routes.

## Impact

- **Code (host):** new `src/omrg/integrations/pdf/maths_pages.py`, `src/omrg/integrations/pdf/maths_routing.py` and `src/omrg/integrations/ocr_worker/routes.py`. `ocr_routing.py` takes a mapping of route to client; it is at 452 lines, so the new logic goes in the new modules. There are also new settings in `config/` and `core/settings.py`, route composition in `capabilities.py`, and the identity changes in `core/ingestion/ocr_identity.py`.
- **Code (worker):** `ocr-worker/` becomes `ocr-workers/{core,engines/paddleocr-vl,engines/dots-mocr}`, plus one `provision.py`. The byte-identity test between the host and worker protocol copies moves to the new path.
- **Dependencies:** no new OMRG core dependency. The dots.mocr engine environment adds torch, torchvision, transformers 4.57.6, accelerate, qwen_vl_utils, huggingface_hub, pypdfium2 and pillow.
- **Licence (dots.mocr agreement, MIT-based):** commercial and on-premises use is allowed. OMRG downloads the weights at provision time and does not redistribute them. Terms the operator accepts at provisioning:
  - 3.3(c): no unauthorised digitisation of publications, document scanning or bulk scraping. Use involving publications needs permission. **This now covers every OCR route, including scanned books.**
  - 5.2: processing sensitive personal data needs a lawful basis.
  - 9: the licensor may revise the terms; licensees must migrate within 90 days.
  - 8: the agreement is governed by the law of the People's Republic of China, with arbitration in Hangzhou.

  Clause 1.6 says MIT prevails on conflict. This is a record of the terms, not legal advice. PaddleOCR-VL is Apache-2.0. An operator who does not accept the dots.mocr terms can leave it unprovisioned, and PaddleOCR-VL then serves every route as the fallback.
- **Hardware:** dots.mocr uses about 7–9 GB of MPS memory in bfloat16 on Apple Silicon, and is slower on CPU. The request timeout scales per page.
- **Data:** a one-off re-ingest after upgrade (identity schema +1). If `normalise-reader-markdown` lands in the same release, the two changes share one schema bump.
- **Operations:** the worker folder moves. Operators re-provision with `python3 ocr-workers/provision.py dots-mocr --accept-model-licence` and `python3 ocr-workers/provision.py paddleocr-vl`. The Paddle model cache moves with it, or `OMRG_OCR_MODEL_CACHE` points at the preserved copy (`ocr-worker/DATA_LOCATIONS.md`).
- **Order:** implementation starts after `page-level-ocr-routing` archives (its `pdf-reader` delta is this change's baseline) and after Experiment 34 closes.
- **Out of scope:** GPU or CUDA provisioning; maths detection that does not use font evidence (for example equations drawn as vector paths or images on born-digital pages).
