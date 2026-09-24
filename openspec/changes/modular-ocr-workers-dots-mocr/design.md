# Design

## Context

See proposal.md (Why). The current state that shapes the approach:

- **Worker project.** `ocr-worker/` is one Paddle-specific project. `worker.py` imports `PaddleOCRVL` lazily. `capabilities.py` declares Paddle packages and identities statically. `protocol.py` and `validation.py` are generic, and the host keeps a byte-identical twin of `protocol.py` in `src/omrg/integrations/ocr_worker/`. The Paddle weights (1.9 GB) sit in the gitignored `ocr-worker/.model-cache/`, and a preserved copy lives outside the repository (`DATA_LOCATIONS.md`).
- **Host side.** `capabilities.build_managed_ocr_client` builds ONE `ManagedOcrClient` from the flat settings `ocr_worker_command`, `ocr_worker_env_dir` and `ocr_worker_request_timeout`. `OcrRoutedPdfInspector` (`integrations/pdf/ocr_routing.py`, 452 lines) takes one `ocr_client`. The document unit sends the whole PDF. The page unit escalates pages through the local tier to the worker (`page-level-ocr-routing`, not yet archived).
- **Timeout.** The host uses one per-request timeout, 300 s by default. dots.mocr takes 7–56 s per page on MPS, so a 14-page whole-PDF request would time out.
- **Evidence for detection.** `eq01` p11 uses CMEX10, CMMI7, CMMI10, CMMIB7, CMMIB10 and CMSY10. `eq01` p1 uses only Nimbus and Times. `pypdf` (already a core dependency, floored at 6.16.1 for a traversal CVE) reads these names in milliseconds. pdf-inspector reports `needs_ocr=False` for p11, so no existing gate sees it.
- **Metadata.** Diagnostic keys stay out of embedded text through `EXCLUDED_EMBED_METADATA_KEYS` (`core/ingestion/embed_exclusions.py`). The exclusion set is part of the index identity.

## Goals / Non-Goals

**Goals:**

- A new engine is one folder under `ocr-workers/engines/` plus a route setting. The host resolves engines by name only (Invariant 11: no `if/elif` over engine names).
- dots.mocr serves every OCR route by default, offline and from a pinned revision, on MPS where available. PaddleOCR-VL takes over only when dots.mocr is unavailable.
- Maths routing reuses the existing page-listed protocol 1.1. No protocol version change.

**Non-Goals:**

- Maths detection without font evidence: equations drawn as vector paths or embedded images on born-digital pages.
- Idle shutdown of engine subprocesses. Routes stay lazy and long-lived, as today.
- CUDA or vLLM serving.

## Decisions

### D1 — Layout: `ocr-workers/{core, engines/<engine>}`, one provisioning script

```
ocr-workers/
  README.md                 how to add an engine (checklist)
  provision.py              python3 provision.py <engine> [--python X.Y] [--accept-model-licence] [--dry-run]
  core/                     package omrg-ocr-worker-core (stdlib + pypdf)
    src/omrg_ocr_worker_core/{protocol,validation,framing,capabilities,pages,engine}.py
  engines/paddleocr-vl/     pyproject.toml, uv.lock, src/omrg_ocr_paddleocr_vl/engine.py, smoke evidence
  engines/dots-mocr/        pyproject.toml, uv.lock, src/omrg_ocr_dots_mocr/{engine,layout,patches}.py, LICENCE-NOTES.md
```

Each engine's `pyproject.toml` depends on the core through a uv path source (`omrg-ocr-worker-core = { path = "../../core" }`). The engine registers itself with one entry point: `[project.entry-points."omrg.ocr_engine"] <name> = "<module>:ENGINE"`. The core's `python -m omrg_ocr_worker_core` loads the single registered engine, or reports unavailable if there are zero or several.

- Alternative: one environment with every engine. Rejected. Paddle and PyTorch runtimes are multi-gigabyte and pin conflicting packages, and one broken engine would break the others.
- Alternative: copy the protocol into each engine. Rejected. That is the drift the host twin test exists to stop, and it would multiply with every engine.

### D2 — Engine contract

```python
class OcrEngine(Protocol):
    name: str                                  # "paddleocr-vl", "dots-mocr"
    backend_id: str                            # diagnostics: "paddleocr_vl", "dots_mocr"
    declared_packages: tuple[str, ...]
    pipeline: tuple[str, str]                  # identity, revision
    model: tuple[str, str]
    def parse(self, pdf: Path, pages: Sequence[int] | None) -> list[str]: ...  # one Markdown string per page
```

The core owns everything else: framing, validation, subset-PDF writing for page lists (TDR-027), error mapping, and the capability command, built from the engine's static fields without importing model code. An engine returns `""` for a page it cannot read, and the core passes that through. The capability payload gains `backend_id`, so the host can stamp diagnostics without knowing engine names.

### D3 — Host routes: primary and fallback, no engine branches

New module `integrations/ocr_worker/routes.py`:

- `resolve_route_command(engine, settings) -> list[str]`. The command is `<OCR_WORKERS_DIR>/engines/<engine>/.venv/bin/python -m omrg_ocr_worker_core`, with `cwd` set to the engine folder. For the primary route, a non-empty `OCR_WORKER_COMMAND` (with `OCR_WORKER_ENV_DIR`) wins, which keeps today's installs working.
- `build_route_clients(settings) -> OcrRoutes`, a frozen pair `(primary, fallback)` of `ManagedOcrClient`. A fallback that resolves to the same command as the primary shares its client. Each client is probed and cached as today.
- `OcrRoutes.select() -> ManagedOcrClient | None` returns the primary if its fingerprint is available, else the fallback if available, else `None`. Selection happens once per dispatch and before it. After dispatch there is no switch (spec: no cross-route retry).
- New settings (flat, beside the existing OCR fields, in `config/` and `EffectiveSettings`):
  - `ocr_workers_dir: str = ""`
  - `ocr_engine_primary: str = "dots-mocr"`
  - `ocr_engine_fallback: str = "paddleocr-vl"`
  - `ocr_maths_routing_enabled: bool = True`
  - `ocr_maths_page_fraction: float = 0.10`
  - `ocr_worker_seconds_per_page: float = 120.0`
- Request timeout: `max(ocr_worker_request_timeout, pages × ocr_worker_seconds_per_page)`, computed per request. For a whole-PDF request, `pages` is the page count.
- `OcrRoutedPdfInspector` takes `ocr_routes: OcrRoutes`. The old `ocr_client=` keyword maps to a primary-only `OcrRoutes` for callers and tests. Every existing dispatch site (document unit, page-unit escalation) calls `ocr_routes.select()` in place of the single client.

### D4 — dots-mocr engine

- **Model:** `rednote-hilab/dots.mocr`, pinned to revision `e539fbb52280393adc081b289ec597430a0f9031` (the revision Experiment 34 measured). `provision.py` downloads it into the engine cache. The worker sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before any import.
- **Apple Silicon patches**, applied once at provisioning by `patches.py`:
  1. make the top-level `flash_attn` import optional, matching at line start only (the Experiment 34 bug fix);
  2. set the vision tower's attention to SDPA.

  Provisioning then records a SHA-256 of every model code file. At start-up the worker refuses to load if a hash differs, because `trust_remote_code` executes these files. The patch-set name joins `pipeline.revision`.
- **Runtime:** MPS when available, else CPU; bfloat16; greedy decoding; `max_new_tokens` 8192. Pages are rendered with pypdfium2 at 200 DPI, raised so the long side is at least 1600 px. This matters for small scanned page boxes: at plain 200 DPI, `io06` rendered at 384 × 624 px and misread words (A2). The prompt is upstream `prompt_layout_all_en`.
- **Output (`layout.py`):** the probe's converter, plus two changes. Page-header and page-footer regions are dropped (upstream's `_nohf` behaviour; Experiment 34's checklist counts page furniture as a problem). Each formula gets exactly one pair of `$$`. A page that hits the token cap, or whose JSON does not parse, returns `""` and logs the reason on standard error.
- **Pins:** transformers 4.57.6 (the version the model code targets), torch ≥ 2.7, qwen_vl_utils, pypdfium2 and pillow, all resolved in the engine's own `uv.lock`.
- Alternative: vendor the model code into the repository. Rejected. The licence requires the notices to be kept, and the upstream fixes would have to be tracked by hand. A pinned revision plus hash verification gives the same safety.

### D5 — Maths-page detector (`integrations/pdf/maths_pages.py`)

- `maths_font_pages(file) -> frozenset[int]` reads each page's `/Resources /Font` through `pypdf`, recursing into Form XObjects with a visited set and a depth cap of 4.
- A font matches when its `/BaseFont`, with any `ABCDEF+` subset prefix stripped and spaces and hyphens normalised, matches one pattern in `MATHS_FONT_PATTERNS`. The Unicode map is not consulted. The patterns are:

  | Family | Pattern |
  | --- | --- |
  | Computer Modern maths | `^(CMMI\|CMMIB\|CMSY\|CMBSY\|CMEX)\d+$` |
  | Latin Modern maths | `^LMMath(Italic\|Symbols\|Extension)\d+`, `^LatinModernMath` |
  | AMS and Euler | `^(MSAM\|MSBM\|EUFM\|EUSM\|EUEX)\d+$` |
  | OpenType maths | `^(CambriaMath\|STIXMath\|STIXTwoMath\|XITSMath\|TeXGyre\w+Math\|LibertinusMath\|AsanaMath\|FiraMath)` |

- `MATHS_DETECTOR_VERSION = 1`. A test pins the pattern tuple to the version, so a list change without a bump fails. Experiment 37 (tasks 7.x) may extend the list, for example with the newtx and newpx maths fonts. Any extension is a version bump.
- Any exception from pypdf returns the empty set and logs once at debug level.
- It runs only on the pdf-inspector path, only when maths routing is enabled, and once per PDF.
- Alternative: ask pdf-inspector for font data. Rejected for now. Its page objects expose only `markdown`, `needs_ocr`, `ocr_reason` and `page`.
- Alternative: detect maths from the extracted text (symbol density). Rejected. pdf-inspector drops the very symbols such a heuristic would count (35 of 35 Greek letters lost on `eq01` p11).

### D6 — Routing integration (`integrations/pdf/maths_routing.py`)

`ocr_routing.py` is near the 500-line ceiling, so the decisions live in a new module that the seam calls:

- `maths_condition(maths_pages, page_count, settings) -> bool` applies the document-unit fraction, with `0.0` as the disabled sentinel. The seam ORs it with `ocr_required_by_gate`. A selected PDF dispatches whole through `ocr_routes.select()`.
- `split_page_routes(flagged, maths_pages) -> (dispatch, local)`. Under the page unit, maths pages leave the local-tier set. They join the escalated pages in the one page-listed request that goes through `ocr_routes.select()`. A page for which the engine returns `""` keeps native text and counts as unresolved.
- A post-dispatch failure raises `OcrPostDispatchError` exactly as today.
- `ocr_backend` takes the answering client's `backend_id` from its fingerprint, and `merge_pages` already yields `mixed`. The constant `OCR_BACKEND_WORKER_PATH` goes away.

### D7 — Identity and embedding exclusion

- The existing `ocr_worker_fingerprint` becomes the primary route's fingerprint. A new `ocr_fallback_fingerprint` sits beside it. Both are built in `core/ingestion/ocr_identity.py`, and an unconfigured route contributes `_UNAVAILABLE_FINGERPRINT_PAYLOAD`.
- A new `"maths_routing": {"enabled", "page_fraction", "detector_version"}` block is present for every source.
- `pages_maths_font` joins `EXCLUDED_EMBED_METADATA_KEYS`.
- `_INDEX_IDENTITY_SCHEMA` advances by one. If `normalise-reader-markdown` ships in the same release, both use the same single bump (6), and the second change to land adds its block without another bump.
- The fingerprint's declared package list for PaddleOCR-VL gains `omrg-ocr-worker-core` and loses `omrg-ocr-worker`. The schema bump already forces the re-ingest.

### D8 — Model cache location

Each engine uses `<engine folder>/.model-cache/` (gitignored). The core honours one variable, `OMRG_OCR_MODEL_CACHE`: when set, engine `<name>` uses `$OMRG_OCR_MODEL_CACHE/<name>/`. This keeps weights outside worktrees (Critical Gotcha #15). Engines set their runtime cache variables from this value by assignment, as the Paddle worker does today (`PADDLE_PDX_CACHE_HOME`, `PADDLE_OCR_BASE_DIR`; `HF_HOME` for dots-mocr).

### D9 — Provisioning and the licence gate

An engine's `pyproject.toml` may declare `[tool.omrg-ocr] licence-file = "..."` and `requires-acceptance = true`. `provision.py` refuses such an engine without `--accept-model-licence`, before installing anything, and prints the licence file path. After `uv sync --locked`, provisioning runs the engine's optional `omrg-ocr-fetch` console script inside the engine environment, to download pinned weights and apply patches. Python range and dry-run behaviour stay as today.

## Risks / Trade-offs

- [The scanned-page evidence for dots.mocr is thin: 2 `io06` pages, with verdicts still open. On near-blank `io06` p53, dots.mocr emitted bleed-through noise and page numbers, where the worker returned nothing (A2).] → The operator decided on 2026-09-24. Experiment 37 (task 7.2) compares both engines on the Experiment 34 scanned pages and reports any page where dots.mocr adds noise. Switching back is one setting (`OCR_ENGINE_PRIMARY=paddleocr-vl`).
- [Licence clause 3.3(c) forbids unauthorised digitisation of publications and document scanning. With dots.mocr primary, this now covers scanned books and papers.] → The gate at provisioning names it. The route only exists once the operator provisions and accepts. `LICENCE-NOTES.md` records clauses 3.3(c), 5.2, 8 and 9. An operator who does not accept leaves dots.mocr unprovisioned, and PaddleOCR-VL serves as the fallback. This is not legal advice.
- [`trust_remote_code` executes downloaded model code] → Pinned revision, hash check at start-up, and an offline parse.
- [dots.mocr uses about 7–9 GB of MPS memory] → Only the primary is normally resident; the fallback starts only when the primary is unavailable. An operator short of memory sets `OCR_ENGINE_PRIMARY=paddleocr-vl`, which is recorded in the configuration guide.
- [CPU-only machines: dots.mocr is slow] → The same setting applies. The per-page timeout scaling keeps long requests from being cut off.
- [The detector over-flags: any inline `$n$` loads a maths font, so a maths paper routes nearly every page] → Accepted. dots.mocr reads prose well, and the cost is time, not text. Experiment 37 measures the flagged share per paper.
- [A maths-font name the list does not know, for example the newtx maths fonts] → The page stays on its normal route, which is today's behaviour. Experiment 37 lists the unmatched font names on maths pages, and extending the list is a version bump.
- [An existing `OCR_WORKER_COMMAND` pointing at PaddleOCR-VL keeps PaddleOCR-VL as the primary] → The configuration guide and release notes tell operators to unset it and set `OCR_WORKERS_DIR`. A start-up log line names the resolved primary and fallback engines.
- [Moving `ocr-worker/` breaks operator scripts] → The migration plan re-provisions. `OCR_WORKER_COMMAND` keeps working when it points at the new path.

## Migration Plan

1. Move `ocr-worker/` to `ocr-workers/engines/paddleocr-vl/` with `git mv`, and extract the core in the same commit so history follows the files.
2. Operators run `python3 ocr-workers/provision.py dots-mocr --accept-model-licence` (downloads about 5.7 GB) and `python3 ocr-workers/provision.py paddleocr-vl`. Then they set `OCR_WORKERS_DIR` and unset `OCR_WORKER_COMMAND`.
3. Every source re-ingests once (identity schema +1).
4. Rollback of the engine choice: set `OCR_ENGINE_PRIMARY=paddleocr-vl`. Rollback of maths routing: set `OCR_MATHS_ROUTING_ENABLED=false`. Both change the identity, so sources reprocess. Reverting the release restores the old layout; re-provision `ocr-worker/` from the old lockfile.
