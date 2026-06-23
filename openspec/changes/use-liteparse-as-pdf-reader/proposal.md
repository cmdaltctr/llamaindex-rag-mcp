## Why

The PDF parsing path is the weakest link in the ingestion pipeline. `llama-index-readers-file>=0.2.0` resolves to `pypdf` (confirmed in `uv.lock:2872`), which is the slowest and lowest-quality model-free PDF parser in every published benchmark — and it discards layout entirely, producing garbage on the two-column academic PDFs that dominate this project's corpus. Meanwhile, Ollama embeddings — the actual ingestion bottleneck — operate on the text pypdf produces, so noisy text degrades both ingest speed (more tokens to embed) and retrieval quality (worse vectors, worse reranker inputs).

LiteParse (run-llama/liteparse v2.0, Rust + PDFium, Apache-2.0) is the best model-free parser available under this project's hard constraints (`🚫 Never: PyTorch at runtime. ONNX Runtime only.`). It blocks Docling, Marker, Unstructured, and MinerU. Of the remaining field, only LiteParse delivers spatial text with bounding boxes, ~3 ms/page parsing (vs pypdf's much higher baseline), and column-aware reading order.

This change introduces a **pluggable PDF reader architecture** so the parser choice becomes a config knob rather than a hard-coded dependency, with LiteParse as the default. The factory pattern accommodates future swaps (pypdfium2 fallback, spdf if it matures, docling-onnx if it ships) without re-architecting. Scope is deliberately limited to PDF; LiteParse's docx/pptx (via LibreOffice roundtrip) and image (via ImageMagick + Tesseract) paths are architecturally enabled but activated in separate follow-on changes, each with their own experiment and ADR.

## What Changes

- **Add** a new `pdf-reader` capability backed by a `readers/` module containing a `BaseReader` protocol, a factory function, and adapter implementations (`pypdf_reader.py`, `liteparse_reader.py`, `pypdfium_reader.py` as fallback).
- **Add** `PDF_READER` environment variable to `config.py` with values `auto | liteparse | pypdfium2 | pypdf`, mirroring the existing `HYBRID_SPARSE_BACKEND` resolver pattern (`config.py:138-160`). `auto` resolves to the first-available adapter in preference order: `liteparse → pypdfium2 → pypdf`.
- **Add** `liteparse` as an optional core dependency in `pyproject.toml` under a `[project.optional-dependencies]` extra (e.g. `pdf-liteparse`) so the baseline install footprint stays small and LiteParse's native build (PDFium auto-download) only runs when explicitly requested.
- **Wire** the factory into `ingestion.py:257` by passing a `file_extractor={".pdf": get_pdf_reader()}` mapping to `SimpleDirectoryReader`. No other ingestion logic changes.
- **Preserve** the existing pypdf path as the default when LiteParse is not installed (`PDF_READER=auto` and `liteparse` import fails → falls back to pypdf via `llama-index-readers-file`). Zero behaviour change for users who do not opt in.
- **Capture** bounding-box metadata from LiteParse on each emitted `Document` (page number, column, section bbox) so downstream retrieval can expose citation provenance. Retrieval-side consumption of bbox is **out of scope** for this change; this is purely metadata capture for future use.
- **Add** ADR-020 recording the LiteParse adoption decision, alternatives considered, and the experiment that validated it.

### In scope
- Factory architecture supporting all formats from day one.
- LiteParse adapter for **PDF only**, activated by default when installed.
- `PDF_READER` env var with `auto` resolution and graceful degradation.
- Experiment 11 (`experiments/11-liteparse-pdf-quality-2026-06-20/`) as the validation gate.
- ADR-020.

### Out of scope but architecturally enabled
- **docx/pptx via LiteParse** (LibreOffice roundtrip): separate change with Experiment 12 to weigh bbox value against the ~5–10 s/file LibreOffice cost vs `python-docx`/`python-pptx`.
- **Image support via LiteParse** (ImageMagick + Tesseract): net-new capability (currently unsupported — `SUPPORTED_EXTENSIONS` excludes images), separate change with OCR strategy decision and Experiment 13.
- **Retrieval-side bbox consumption** (citation highlighting, layout-aware retrieval, figure-caption linking): separate change once bbox metadata is flowing through the pipeline.

### Non-goals
- No change to chunking strategy (`SentenceSplitter` remains). Layout-aware chunking is a follow-on once bbox metadata is proven valuable.
- No change to reranker or hybrid retrieval paths. Cleaner PDF text is expected to improve both as a side effect; this is measured, not designed.
- No change to `SUPPORTED_EXTENSIONS`. PDF scope unchanged.

## Capabilities

### New Capabilities
- `pdf-reader`: Pluggable PDF document parsing with spatial-aware text extraction, bounding-box metadata capture, and graceful fallback across multiple parser backends (pypdf, pypdfium2, LiteParse).

### Modified Capabilities
None. The change is purely additive at the spec level. `async-ingestion`, `metadata-extraction`, and `markdown-aware-chunking` requirements are unchanged — this change alters which reader is *invoked* inside the existing async path, not the async contract, the metadata contract, or the chunking contract.

## Impact

**Affected code:**
- `src/rag_mcp/config.py` — add `PDF_READER` env var and `_resolve_pdf_reader()` resolver following the `HYBRID_SPARSE_BACKEND` pattern.
- `src/rag_mcp/readers/` (new module) — `base.py`, `factory.py`, `pypdf_reader.py`, `pypdfium_reader.py`, `liteparse_reader.py`.
- `src/rag_mcp/ingestion.py:257` — pass `file_extractor={".pdf": get_pdf_reader()}` to `SimpleDirectoryReader`. ~3-line change.
- `pyproject.toml` — add `pdf-liteparse` optional-dependencies extra.
- `.env.example` — document `PDF_READER` and the `[pdf-liteparse]` install flag.
- `tests/unit/test_pdf_reader_factory.py` (new) — factory resolution, fallback, error handling.
- `tests/unit/test_liteparse_reader.py` (new) — adapter behaviour, bbox capture, malformed-PDF handling.
- `docs/adr/020-use-liteparse-as-pdf-reader.md` (new).
- `docs/guides/` — update ingestion guide to mention `PDF_READER` knob.

**New dependencies:**
- `liteparse` (PyPI, Apache-2.0) — optional, gated behind `[pdf-liteparse]` extra. Brings native PDFium binary (auto-downloaded at install).
- No new system-level dependencies for PDF scope. (LiteParse's LibreOffice/ImageMagick paths are not used in this change.)

**Affected APIs:**
- No public MCP API change. `ingest_documents`, `search_documents`, etc. behave identically from the client perspective; only ingestion internals change.
- No CLI change.

**Risk vectors:**
- **Native build flakiness**: PDFium auto-download during `pip install liteparse` can fail on some platforms. Mitigated by `auto` fallback to pypdf and CI matrix testing.
- **Two-column reading order regression**: third-party benchmarks report LiteParse v2 occasionally merges columns on certain PDF layouts. Mitigated by Experiment 11 pass-gate on real academic corpus.
- **Early-adopter risk on v2.0**: Rust rewrite shipped recently; less battle-tested than PyMuPDF's decade. Mitigated by factory pattern enabling easy swap if LiteParse disappoints.
- **MCP tool error contract**: any LiteParse failure inside `ingest_documents` must surface as `{"status": "error", "message": "..."}`, never an exception. Explicit requirement in spec.

**Validation gate:** Experiment 11 (`experiments/11-liteparse-pdf-quality-2026-06-20/`) must PASS before LiteParse becomes the `auto` default. Until the experiment passes, `PDF_READER=pypdf` remains the implicit default and LiteParse is opt-in only.

**Reversibility:** If LiteParse underperforms, the change is fully reversible by setting `PDF_READER=pypdf` (or uninstalling the `[pdf-liteparse]` extra). The factory architecture is retained as durable infrastructure regardless of LiteParse's fate.
