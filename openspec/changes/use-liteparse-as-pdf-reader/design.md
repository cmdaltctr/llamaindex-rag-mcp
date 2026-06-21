## Context

The current PDF parsing path in `src/rag_mcp/ingestion.py:257` uses LlamaIndex's `SimpleDirectoryReader` with no `file_extractor` override, which resolves through `llama-index-readers-file>=0.2.0` (pinned in `pyproject.toml`) to **`pypdf` 6.11.0** (confirmed in `uv.lock:2872`). `pypdf` is consistently the slowest and lowest-quality model-free PDF parser in published benchmarks; it also discards all layout information, producing interleaved garbage on the two-column academic PDFs that dominate this project's target corpus.

This change introduces a pluggable reader architecture with LiteParse (`run-llama/liteparse` v2.0, Rust + PDFium, Apache-2.0) as the default candidate. LiteParse is selected over alternatives because:

1. **Hard-constraint compatibility** — no PyTorch, no cloud APIs (matches AGENTS.md `🚫 Never` rules). Docling, Marker, Unstructured, and MinerU are blocked by the PyTorch rule; LlamaParse, Mistral OCR, and Firecrawl are blocked by the cloud rule.
2. **Best-in-class for the surviving field** — pypdf, pypdfium2, PyMuPDF4LLM, and LiteParse are the only model-free options under the constraints. Of these, only LiteParse produces spatial text with bounding boxes; only LiteParse is Apache-2.0 (PyMuPDF4LLM is AGPL-3 with distribution risk for self-hosted products).
3. **Vendor alignment** — same team as LlamaIndex (the framework this project already depends on), so integration ergonomics and long-term maintenance are favourable.

The factory architecture deliberately mirrors the existing `HYBRID_SPARSE_BACKEND` resolver pattern at `config.py:138-160`. This is a deliberate reuse of an in-codebase pattern rather than introducing a new abstraction.

The user's stated motivations are (a) ingest speed at scale (100+ documents), (b) retrieval quality on academic PDFs, and (c) future-proofing for spatial RAG capabilities (bbox-grounded retrieval, citation highlighting, figure-caption linking).

## Goals / Non-Goals

**Goals:**
- Make the PDF parser a config-driven choice rather than a hard-coded transitive dependency.
- Activate LiteParse as the default PDF parser, conditional on Experiment 11 validating quality and speed on a real academic corpus.
- Capture bounding-box metadata from LiteParse so future retrieval-side consumption is possible without re-ingesting.
- Preserve zero behaviour change for users who do not opt in (`PDF_READER=pypdf` or `[pdf-liteparse]` not installed).
- Establish the factory pattern that supports docx/pptx/image readers in future changes without re-architecting.

**Non-Goals:**
- No activation of LiteParse's docx/pptx paths (LibreOffice roundtrip) or image paths (ImageMagick + Tesseract). Each is a separate change with its own experiment and ADR.
- No retrieval-side bbox consumption. Capture only.
- No layout-aware chunking. `SentenceSplitter` remains the chunker for all formats.
- No change to `SUPPORTED_EXTENSIONS`. PDF scope unchanged.
- No new system-level dependencies for the PDF scope. LibreOffice and ImageMagick are deferred to follow-on changes.
- No benchmark of LiteParse against VLM-based parsers (LlamaParse, Docling, Marker). The hard PyTorch constraint excludes them by definition.

## Decisions

### Decision 1: Factory pattern with env-var-driven resolution

**Choice.** Introduce a `readers/` module with a `get_pdf_reader()` factory that returns a `BaseReader` adapter based on `PDF_READER` env var. Mirror the `HYBRID_SPARSE_BACKEND` resolver (`config.py:138-160`) including a `RESOLVED_PDF_READER` constant computed once at import.

**Rationale.**
- The codebase already has a validated pattern for exactly this shape of problem (`HYBRID_SPARSE_BACKEND` → `_resolve_sparse_backend()` → `RESOLVED_HYBRID_SPARSE_BACKEND`). Reusing it is the boring, readable choice AGENTS.md prefers.
- A factory isolates the parser choice from the ingestion call site. `ingestion.py:257` becomes a one-line change (`file_extractor={".pdf": get_pdf_reader()}`) instead of a branching mess.
- Future readers (pypdfium2, spdf, docling-onnx, pymupdf-markdown) plug in via one adapter file each. No re-architecture.

**Alternatives considered.**
- *Hard-coded LiteParse, no factory.* Rejected — couples ingestion to a single parser, makes future swaps expensive, contradicts the user's "future-proof" requirement.
- *LlamaIndex's built-in reader discovery.* Rejected — LlamaIndex's `SimpleDirectoryReader` does pick up installed readers, but the precedence is opaque and not config-driven. An explicit factory keeps the resolution logic in this codebase.
- *Plugin/registry system with entry points.* Rejected — over-engineered for a handful of adapters. Plain `if/elif` in the factory is simpler and matches the sparse-backend pattern.

### Decision 2: PDF-only scope; docx/pptx/image paths deferred

**Choice.** Wire LiteParse into the factory for `.pdf` only. docx and pptx continue through `python-docx` and `python-pptx` via `SimpleDirectoryReader`. Images remain unsupported.

**Rationale.**
- **The hypothesis under test is PDF-specific.** The user's corpus is academic PDFs; bbox value is highest there (two-column layouts, tables, captions). Mixing formats into one experiment confounds results.
- **docx via LiteParse is a net speed regression.** LiteParse's docx support shells out to LibreOffice (5–10 s/file cold start) vs `python-docx` (~0.1 s/file). Justifying that cost requires its own experiment weighing bbox value against speed loss.
- **Image support is net-new.** `SUPPORTED_EXTENSIONS` excludes images today; adding them is a feature, not a swap, and demands an OCR strategy decision (Tesseract via LiteParse vs Ollama with `llama3.2-vision`) that deserves its own design discussion.
- **Smaller changes are more reversible.** Per OpenSpec philosophy and AGENTS.md's "ask before big-bang refactors" rule.

**Alternatives considered.**
- *Activate all LiteParse-supported formats in one change.* Rejected — three confounded variables in one experiment, larger blast radius, harder rollback.
- *Activate PDF + docx, defer images.* Rejected — still mixes PDF validation with a docx speed regression that hasn't been justified.

### Decision 3: LiteParse as `[pdf-liteparse]` optional dependency

**Choice.** Add `liteparse` to `pyproject.toml` under `[project.optional-dependencies]` as `pdf-liteparse`, not as a core dependency. Baseline `uv sync` does not install it.

**Rationale.**
- **Respects AGENTS.md** `⚠️ Ask: Adding new core dependencies`. By gating LiteParse behind an extra, the baseline install footprint is unchanged and the user opts in explicitly.
- **Native build isolation.** LiteParse's install pulls a PDFium binary via `pyo3`/`maturin`. If that build fails on a given platform (notably Windows CI runners), the baseline install and test suite still work — they fall back to pypdf.
- **Matches the project's existing pattern** of optional dependencies for hybrid retrieval (`fastembed`, `bm25s` are extras, not core).
- **CI strategy.** Tests pin `PDF_READER=pypdf` for the default job; a separate job installs `[pdf-liteparse]` and pins `PDF_READER=liteparse` to exercise the LiteParse path.

**Alternatives considered.**
- *Make `liteparse` a core dependency.* Rejected — violates the "ask before core deps" rule and forces every contributor to build PDFium.
- *Vendor LiteParse in the repo.* Rejected — supply-chain risk, update burden.

### Decision 4: `auto` resolution order is `liteparse → pypdfium2 → pypdf`

**Choice.** When `PDF_READER=auto` (proposed default after Experiment 11 passes), the resolver probes imports in this order and returns the first available.

**Rationale.**
- **LiteParse first** because it is the change's whole point — bbox, speed, quality.
- **pypdfium2 second** as a same-engine fallback (both use PDFium). If LiteParse's binary build fails but pypdfium2 (pure-Python wheel) installs, the user still gets PDFium-grade parsing without bbox.
- **pypdf last** as the always-available floor. If neither extra is installed, behaviour is identical to today.

**Alternatives considered.**
- *Order: pypdfium2 → liteparse → pypdf.* Rejected — pypdfium2 lacks bbox; we want bbox when available.
- *Including PyMuPDF as an accepted value.* Rejected — PyMuPDF is AGPL-3, incompatible with this project's self-hosted distribution model. Excluded entirely from accepted values and from the `auto` order. PyMuPDF4LLM is noted as an alternative in ADR-020 for future projects without the AGPL constraint.

### Decision 5: Bbox metadata capture now, consumption later

**Choice.** LiteParse adapter emits `Document.metadata` containing `page`, `column`, `section_bbox`, and per-text-item coordinates. Retrieval code does not read these fields in this change.

**Rationale.**
- **Avoids re-ingestion cost.** Capturing bbox during ingest is cheap; re-ingesting later to add bbox is expensive (especially at 100+ documents with Ollama embeddings).
- **Decouples capture from consumption.** This change is already non-trivial; bolting on retrieval-side bbox consumption would explode scope. A follow-on change can iterate on retrieval without touching ingestion.
- **Honest about value.** Bbox value is hypothetical until retrieval code uses it. Capture is a low-risk enabler; consumption is the actual experiment.

**Alternatives considered.**
- *Defer bbox capture to the consumption change.* Rejected — forces re-ingestion of the entire corpus.
- *Capture and consume in one change.* Rejected — violates single-responsibility and balloons scope.

### Decision 6: Experiment 11 as a hard validation gate

**Choice.** LiteParse becomes the `auto` default **only after** Experiment 11 (`experiments/11-liteparse-pdf-quality-2026-06-20/`) passes its pre-registered pass gates. Until then, `PDF_READER=pypdf` is the implicit default.

**Rationale.**
- **Matches the project's existing discipline.** ADR-018 was informed by Experiments 7a/8a; ADR-019 by Experiments 9a/10. LiteParse adoption should follow the same pattern.
- **Pre-registration prevents post-hoc reasoning.** Pass gates are written before the experiment runs (per `/s-experiment` skill), so "did LiteParse win?" has an objective answer.
- **Forces corpus assembly.** The user's corpus composition is currently unknown. The experiment demands ~20 academic PDFs be assembled, which doubles as a permanent test fixture.

**Pass gates (pre-registered):**
- **Quality win:** nDCG@10 on candidate-B (LiteParse) ≥ baseline-A (pypdf) + 5% relative.
- **Speed win:** total ingest wall-clock for candidate-B ≤ baseline-A × 0.80.
- **Regression guard A:** nDCG@10 on candidate-B-r (LiteParse + reranker) ≥ candidate-B (reranker should still help).
- **Regression guard B:** zero queries move from "found" (in top-K) to "not found" between baselines and candidates.

**Alternatives considered.**
- *Adopt LiteParse without an experiment.* Rejected — third-party benchmarks report two-column reading-order regressions on some layouts. Without our own measurement, we cannot distinguish "LiteParse helped" from "LiteParse hurt on our specific corpus".
- *Use Experiment 11 as advisory only.* Rejected — advisory experiments get ignored. The hard gate forces a real decision.

### Decision 7: ADR-020 records the decision regardless of outcome

**Choice.** Whether Experiment 11 passes or fails, write ADR-020 documenting the decision, the alternatives considered, the experiment outcome, and the rationale.

**Rationale.**
- **Failure is also a decision.** If LiteParse disappoints, ADR-020 captures *why* so future contributors do not relitigate.
- **Factory pattern is durable regardless.** Even if LiteParse is rejected, the pluggable architecture remains useful and the ADR records its genesis.

## Risks / Trade-offs

| Risk                                                        | Mitigation                                                                                                                                                    |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PDFium binary build flakiness** on Windows / older Linux  | `[pdf-liteparse]` extra isolates the build. `auto` falls back to pypdfium2 or pypdf. CI runs a separate LiteParse job; main job stays on pypdf.               |
| **Two-column reading-order regression** on academic PDFs    | Experiment 11 pass-gate explicitly tests this on real academic corpus. LiteParse not promoted to `auto` default until gate passes.                             |
| **LiteParse v2.0 maturity** (Rust rewrite shipped recently) | Factory pattern enables swap to pypdfium2 or future spdf/docling-onnx if LiteParse disappoints. No lock-in.                                                   |
| **AGPL contamination** from PyMuPDF                        | PyMuPDF (AGPL-3) is structurally excluded — not in accepted `PDF_READER` values, not in `auto` order, no adapter shipped. Documented in ADR-020.               |
| **Lock-in to LiteParse bbox schema**                        | Bbox metadata stored with versioned keys (`page`, `column`, `section_bbox`, `text_items`) that map cleanly to alternative parsers' output. Adapter-isolated. |
| **MCP error contract violation** (LiteParse raises)         | Explicit spec requirement: every LiteParse failure inside `ingest_documents` MUST surface as `{"status": "error", "message": "..."}`, never an exception.    |
| **Corpus assembly blocker** for Experiment 11               | Experiment skeleton (protocol.md, ground_truth.json stub, runner pattern) created in this change. User supplies PDFs as the only manual step.                |
| **Confounded ingest metrics** (pypdf vs Ollama bottleneck)  | Experiment measures ingest wall-clock *and* parsing wall-clock separately. Pass-gate is on total ingest, but parsing-only timing is recorded for diagnostics. |
| ** bbox metadata inflates storage** in ChromaDB             | LiteParse bbox is captured as JSON-encoded metadata strings. Estimated <2× metadata size; measured in Experiment 11 and recorded.                            |

## Migration Plan

This change is **opt-in by default and reversible**. There is no breaking migration.

**Pre-experiment (immediately after this change merges):**
- Users who do nothing continue to get pypdf. Zero behaviour change.
- Users who want LiteParse early run `uv sync --extra pdf-liteparse` and set `PDF_READER=liteparse`.

**Post-experiment (after Experiment 11 PASS):**
- A small follow-on change flips `PDF_READER` default from `pypdf` to `auto`.
- Existing users who never installed `[pdf-liteparse]` continue to get pypdf via `auto` fallback. Zero behaviour change.
- Users who install `[pdf-liteparse]` automatically get LiteParse.

**Rollback:**
- Set `PDF_READER=pypdf` to force the legacy path.
- Uninstall `[pdf-liteparse]` extra to remove the native binary.
- The factory architecture remains in place; rollback is a config flip, not a code revert.

## Open Questions

These are flagged in `tasks.md` as decision points but do not block the proposal:

1. **Corpus composition for Experiment 11.** Minimum 20 academic PDFs with two-column layouts? Include scanned PDFs to exercise Tesseract, or exclude them? *Decision: user supplies corpus; suggested mix documented in `experiments/11-liteparse-pdf-quality-2026-06-20/protocol.md`.*
2. **pypdfium2 inclusion in this change vs follow-on.** Adding `pypdfium2` as another optional extra now gives `auto` a useful middle fallback if LiteParse's native build fails on a given platform. *Decision: include in this change. pypdfium2 ships as a pure-Python wheel with bundled PDFium (no Rust build), making it a portable same-engine fallback tier between LiteParse and pypdf. Declared under a separate `[pdf-pypdfium2]` extra so users opt in explicitly.*
3. **Bbox metadata schema versioning.** Should metadata carry a `bbox_schema_version` key for future evolution? *Decision: yes, captured in spec requirement. Cheap insurance.*
4. **LiteParse constructor defaults.** Do we expose `ocr_enabled`, `dpi`, `num_workers` as env vars, or hard-code sensible defaults? *Decision: hard-code defaults for v1; expose `LITEPARSE_OCR_ENABLED` and `LITEPARSE_NUM_WORKERS` as follow-on if needed.*
