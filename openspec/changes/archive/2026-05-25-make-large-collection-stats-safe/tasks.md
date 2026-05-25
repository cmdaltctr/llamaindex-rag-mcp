## 1. Shared Pagination Helper

- [x] 1.1 Add `CHROMA_SCAN_PAGE_SIZE` to `config.py` with default `10000`.
- [x] 1.2 Implement an internal helper to iterate ChromaDB metadata pages using `limit` and `offset`.
- [x] 1.3 Ensure the helper processes one page at a time and handles empty collections cleanly.

## 2. Replace Hardcoded Caps

- [x] 2.1 Update `list_documents()` to aggregate source counts across all metadata pages.
- [x] 2.2 Update `list_collections()` to compute document counts across all metadata pages.
- [x] 2.3 Update `_gather_existing_categories()` to scan all metadata pages for categories.
- [x] 2.4 Remove scattered `limit=10000` literals from these code paths.

## 3. Tests and Verification

- [x] 3.1 Add tests with small `CHROMA_SCAN_PAGE_SIZE` to verify multi-page document listing.
- [x] 3.2 Add tests with small `CHROMA_SCAN_PAGE_SIZE` to verify multi-page collection listing.
- [x] 3.3 Add tests that category lookup discovers categories beyond the first page.
- [x] 3.4 Run the relevant pytest subset and OpenSpec validation.
