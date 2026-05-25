## Context

`list_documents()`, `list_collections()`, and `_gather_existing_categories()` each call `collection.get(include=["metadatas"], limit=10000)` once. The comments acknowledge memory pressure, but callers receive incomplete results with no warning when collections exceed that cap.

## Goals / Non-Goals

**Goals:**
- Centralize the 10,000 fetch size in `config.py`.
- Iterate ChromaDB metadata pages with `limit` and `offset` until all rows are scanned.
- Keep memory bounded by processing one page at a time.
- Add tests covering collections larger than one configured page.

**Non-Goals:**
- Changing ChromaDB storage schema or collection distance metrics.
- Changing default search result ranking.
- Adding a general-purpose analytics subsystem.

## Decisions

- Use a helper such as `_iter_collection_metadatas(collection, page_size)` rather than duplicating pagination loops.
- Define `CHROMA_SCAN_PAGE_SIZE = int(os.getenv("CHROMA_SCAN_PAGE_SIZE", "10000"))` in `config.py` as the central truth for scan page size.
- Prefer full pagination over warning-only truncation for user-facing counts, because incorrect counts are worse than bounded extra reads.
- Keep helper internal unless a public module boundary becomes necessary later.

## Risks / Trade-offs

- Large collections require more ChromaDB reads → mitigate by paging and keeping the default page size high.
- Long category scans during metadata extraction may add latency → mitigate by reusing the cached Chroma client and scanning metadata only, not documents or embeddings.
- Tests with >10,000 chunks would be slow → mitigate by monkeypatching `CHROMA_SCAN_PAGE_SIZE` to a small number.
