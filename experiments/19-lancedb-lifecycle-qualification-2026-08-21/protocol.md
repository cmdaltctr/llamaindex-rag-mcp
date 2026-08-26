# Protocol 1.0 — LanceDB production-lifecycle qualification (campaign 19)

Task 0 of the OpenSpec change `make-lancedb-default-and-isolate-chromadb`.
This campaign is the TDR-014-admissible pause gate that must pass before
the `VECTOR_STORE` default flips from `chroma` to `lancedb`.

## Purpose

Stage 5 adapter-level parity did not exercise every production
ingestion/reopen/mutation path on LanceDB. This campaign runs the real
production entry points (`compose.ensure_runtime_setup`,
`ingest_path_async`, `search`, `remove_document`) against an embedded
LanceDB index with real Ollama embeddings, at a frozen commit and lock,
and records raw per-gate rows plus a manifest under TDR-014 rules.

## Frozen inputs

- Corpus: `fixtures/corpus/` (3 documents: quartz, harbour, lighthouse).
- Replacement variant: `fixtures/corpus_replacement/bravo_harbour.txt`.
- Interrupted-write corpus: `fixtures/corpus_interrupted/`
  (`good_delta.txt` + a deliberately invalid `broken_binary.pdf`).
- Collection: `qual_documents`. Store URI: campaign `output/<run>/lancedb_store`.
- Embedding: `EMBED_PROVIDER=local`, `LOCAL_BACKEND=ollama`,
  `EMBED_MODEL=nomic-embed-text`, `OLLAMA_BASE_URL` from environment
  (default `http://localhost:11434`).
- Sparse backend: explicit `HYBRID_SPARSE_BACKEND=bm25` (LanceDB route).
- Metadata extraction: `METADATA__EXTRACTION_MODE=disabled` (the measured
  path is the store lifecycle, not LLM metadata).
- PDF reader: `pypdf` (deterministic; corpus is non-PDF by design).

## Gates

Each gate MUST pass for the campaign to pass. A gate is `pass` only when
its assertions hold and its raw row is on disk. Any failed, incomplete,
or not-evaluable gate blocks tasks 2.1–2.3 and the default flip.

| Gate | Name | Pass criterion |
| --- | --- | --- |
| G1 | real parse/chunk/embed/write | `ingest_path_async` on the corpus reports every file indexed; collection chunk count > 0; rows record files, chunks, elapsed |
| G2 | restart/reopen | a fresh interpreter (`verify_reopen.py` subprocess) reopens the same URI, observes the same chunk count, and returns a dense hit for the corpus query |
| G3 | dense retrieval | `search(hybrid=False)` returns the expected corpus file as the top hit for each gate query; scores are finite; score kind recorded |
| G4 | BM25 hybrid retrieval | `search(hybrid=True)` returns non-empty fused results for a lexical query; diagnostics record the sparse contribution |
| G5 | metadata filters | a metadata filter restricting to one source file returns only rows from that file; `count_where` agrees |
| G6 | unchanged re-ingest | re-running the identical ingest leaves the chunk count unchanged (change detection reports no new work) |
| G7 | replacement | ingesting the v2 harbour file replaces v1 chunks; a v1-only phrase no longer retrieves the harbour file; a v2 phrase does |
| G8 | document deletion | `remove_document` on the harbour file removes exactly its chunks; count drops accordingly; retrieval no longer returns it |
| G9 | collection deletion | `delete_collection` removes the collection; `list_collections` no longer names it; the collection can be recreated and written again |
| G10 | identity stamping | collection metadata carries the embedding-identity triple matching the manifest embedding identity |
| G11 | generation invalidation | the collection generation counter advances across a mutation; a hybrid query after the mutation returns results consistent with post-mutation data |
| G12 | interrupted-write recovery | ingesting the interrupted corpus (one good file + one invalid PDF) completes with the failure contained to the bad file; the good file is queryable; a subsequent clean ingest is healthy |
| G13 | narrowed-lock concurrent read | a dense search on the populated collection completes without error while an ingestion into a second collection is in flight (TDR-013 lock scope) |
| G14 | manifest + plan agreement | manifest mandatory fields non-null (TDR-014 §1, with permitted nulls reasoned), preflight assertions green, plan cells == executed gates |

## Admissibility

- Runs at a clean git commit (no dirty tree) with the lock hash recorded.
- Raw rows are JSONL, append-only, one row per gate, never regenerated.
- `output/<run>/manifest.json` is written once per run, before gates.
- Verdict file `output/<run>/verdicts.json` is atomic (`.tmp` → rename).
- Exit code 0 only when every gate verdict is `pass`.

## Inadmissible outcomes

- Any gate `fail`, `incomplete`, or `not_evaluable`.
- A run against a dirty tree or an unrecorded lock.
- Missing raw rows for any cited gate.
