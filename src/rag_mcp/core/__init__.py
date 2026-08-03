"""Core RAG framework subpackages.

Phase 1 of the modular refactor extracts the three worst-offender monoliths
into subpackages:

- ``core.metadata`` — metadata extraction backends and orchestrator.
- ``core.ingestion`` — async ingestion pipeline (loader, chunker, writer).
- ``core.chunking`` — chunking strategies (code, markdown, sentence, config).
- ``core.retrieval`` — dense/sparse/fusion/reranker retrieval pipeline.

Each subpackage shares only ``rag_mcp.config`` (AGENTS.md invariant #2).
Legacy top-level modules (``metadata_extractor.py``, ``ingestion.py``,
``retrieval.py``, ``sparse_retriever.py``, ``reranker.py``) remain as
compat shims with ``DeprecationWarning`` until v2.0.0.
"""
