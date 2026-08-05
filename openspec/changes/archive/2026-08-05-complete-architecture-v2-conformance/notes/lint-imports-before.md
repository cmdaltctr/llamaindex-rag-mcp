# `lint-imports` — pre-fix failure state (design.md D7 evidence)

D7 requires each contract be added, **observed failing on its known offender**,
and only then satisfied — so every closed finding has recorded failure as
evidence. That failing state existed at commit `a378b134`, before the
suppression commit `bbf8864a`. This file records it outside a commit diff so a
future auditor does not have to reconstruct it by reverting.

**Reproduce:** remove the seven entries marked `# TEMPORARY` from the
`ignore_imports` lists of `chromadb-confined-to-vectordb`, `config-is-leaf` and
`integrations-are-leaves` in `pyproject.toml`, then run `uv run lint-imports`.
The sanctioned `# PERMANENT` entries (config → `core.*.settings`) and
`core.vectordb.chroma -> chromadb` stay.

Each violation below is closed by a later group; the ignore entry naming that
task is removed at **task 10.3a**, which is gated by
`unmatched_ignore_imports_alerting = "error"` — a stale ignore fails the run.

| Violation | Closed by |
|---|---|
| `core.codebase.codebase_map -> chromadb` (F2) | 6.1 / 6.3 |
| `config -> core.retrieval.sparse` (F3) | 7.10 |
| `integrations.{azure,magika,pdf.factory,pdf.liteparse} -> config` (F4) | 5.6 |
| `integrations.magika -> core.codebase.codebase_map` (F5) | 6.4 / 6.5 |

## Captured output

```
Contracts
---------

Analyzed 144 files, 534 dependencies.
-------------------------------------

settings-models-are-pure-data KEPT
providers-constructed-only-in-compose KEPT
core-business-avoids-providers-transports KEPT
chromadb-confined-to-vectordb BROKEN
config-is-leaf BROKEN
integrations-are-leaves BROKEN

Contracts: 3 kept, 3 broken.


----------------
Broken contracts
----------------

chromadb-confined-to-vectordb
-----------------------------

rag_mcp is not allowed to import chromadb:

-   rag_mcp.core.codebase.codebase_map -> chromadb (l.476)


config-is-leaf
--------------

rag_mcp.config is not allowed to import rag_mcp.core.retrieval:

-   rag_mcp.config -> rag_mcp.core.retrieval.sparse (l.395)


rag_mcp.config is not allowed to import rag_mcp.core.vectordb:

-   rag_mcp.config -> rag_mcp.core.retrieval.sparse (l.395)
    rag_mcp.core.retrieval.sparse -> rag_mcp.core.vectordb (l.166)


integrations-are-leaves
-----------------------

rag_mcp.integrations is not allowed to import rag_mcp.core:

-   rag_mcp.integrations.azure -> rag_mcp.config (l.18)
    rag_mcp.config -> rag_mcp.core.metadata.settings (l.36)

-   rag_mcp.integrations.magika -> rag_mcp.config (l.25)
    rag_mcp.config -> rag_mcp.core.retrieval.settings (l.37)

-   rag_mcp.integrations.magika -> rag_mcp.core.codebase.codebase_map (l.82)

-   rag_mcp.integrations.pdf.factory -> rag_mcp.config (l.34)
    rag_mcp.config -> rag_mcp.core.retrieval.sparse (l.395)

-   rag_mcp.integrations.pdf.liteparse -> rag_mcp.config (l.45)
    rag_mcp.config -> rag_mcp.core.chunking.settings (l.35)


```
