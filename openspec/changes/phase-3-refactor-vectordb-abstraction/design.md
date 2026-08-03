## Context

Phase 3 of the five-phase refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §5.2 vectordb, §8). ChromaDB is used directly across the pipeline. Phase 3 introduces the only genuinely new abstraction of the refactor: a `VectorStore` ABC. The design risk is honest scope — capture what ChromaDB actually does for us without inventing a fantasy of store-portability we have not earned.

## Goals / Non-Goals

**Goals:**

- One ABC (`core/vectordb/base.py`) covering every store operation in use.
- ChromaDB implementation (`core/vectordb/chroma.py`) absorbing `chroma_utils.py` and writer-side collection logic.
- Dimension locking, metadata filters, and generation bumping encoded as contract behaviour.
- `VECTOR_STORE=chroma` selection through config/compose.

**Non-Goals:**

- No second store implementation (LanceDB, Qdrant, pgvector are future work).
- No sparse/BM25 store abstraction — BM25 stays in `core/retrieval/sparse.py` and is out of this interface's scope.
- No migration of existing collections.
- No query-language abstraction beyond the metadata filters currently used.

## Decisions

### D1: Encode ChromaDB behaviours, don't hide them

The ABC documents dimension locking, `where`-clause filtering, and generation bumping as contract-level behaviours. Alternative considered: a minimal "ideal" interface (put/get/delete) that treats these as ChromaDB quirks — rejected because the pipeline depends on all three; pretending otherwise produces an interface that leaks on first alternative implementation (PROPOSAL §5.2: "real design work, not just folder creation").

### D2: Collection metadata is part of the contract

The ABC includes collection metadata read/update. This is load-bearing for Phase 4: profile tags live in collection metadata (`metadata={"profile": "codebase"}`) and `ProfileResolver` reads them through the store. Designing the ABC without it would force a Phase 4 interface revision.

### D3: `chroma_utils.py` is absorbed, not shimmed

The 49-line `chroma_utils.py` merges into `chroma.py`; no compat shim is kept because it is an internal helper, not a public import surface (unlike the Phase 1 modules). Its callers move in the same change.

### D4: Construction in compose, selection in config

`VECTOR_STORE` resolves in `config.py`; `compose.py` constructs the implementation and injects it into the ingestion writer and retrieval pipeline. This follows the Phase 2 three-layer discipline — the pipeline never constructs or imports ChromaDB.

## Risks / Trade-offs

- ABC leaks ChromaDB assumptions anyway → mitigate with the integration test plus ADR 029 recording which behaviours are deliberate contract surface; a second implementation (future) is the real test and will amend the ADR if wrong.
- Interface too thin to be useful → countered by D1 (operations enumerated from actual call sites before writing the ABC).
- Generation-bump semantics diverge during the move → the existing upsert tests are the regression net; they must pass unmodified.
- Scope creep into a second store → explicitly out of scope; the phase ends when ChromaDB passes the contract.

## Migration Plan

1. Enumerate every ChromaDB call site in `core/`; freeze the operation list.
2. Write `base.py` ABC + contract integration test (fails first).
3. Write `chroma.py` absorbing `chroma_utils.py` + writer-side collection logic; make the contract test pass.
4. Rewire writer and pipeline through the injected store; delete `chroma_utils.py`.
5. Run the full fast suite; rollback is a branch revert.

## Open Questions

- Whether collection-metadata update needs optimistic concurrency (two writers bumping generation) — resolved during implementation; ChromaDB's SQLite metadata store makes this a single-node concern only.
