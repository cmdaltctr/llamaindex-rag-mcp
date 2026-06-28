# Fast Context + Document RAG: Design Proposal

## Unified Codebase Intelligence in the RAG MCP

**Date**: 2026-06-26  
**Status**: Proposal — for review in RAG MCP project session  
**Target Project**: `llamaindex-rag-mcp` (`/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp`)  

---

## 1. Purpose

The RAG MCP should do **two things**:

| # | Capability | What it gives agents | Status |
|---|-----------|---------------------|--------|
| **1** | **Fast Context** | A pre-computed codebase map (file types + structural relationships + community clusters) so the agent starts knowing what exists and how it connects — without exploratory `ls`/`glob`/`read_file` calls | **NEW** |
| **2** | **Document RAG** | Semantic retrieval over ingested documents and code, for query-time "find me the relevant chunk" | **EXISTING** (v1.7.0) |

Both capabilities live in the RAG MCP. No external graph tools.

---

## 2. The Problem

When an AI agent starts a session on an unfamiliar codebase, it burns 5-20 
tool calls just to map the project — `list_directory`, `read_file`, `glob`, 
repeated across subdirectories. That's ~2,000+ tokens spent on discovery 
before useful work begins.

**Fast context eliminates this.** The agent starts with a ground-truth map 
showing what files exist, what types they are, and how they connect.

---

## 3. Architecture Overview

The RAG MCP builds a unified knowledge graph during ingestion using two 
strategies — one for code, one for documents:

```
RAG MCP INGESTION PIPELINE
    │
    ├── FOR EACH FILE:
    │   │
    │   ├─ Magika → detect content type
    │   │
    │   ├─ If CODE (typescript, python, php, etc.):
    │   │   ├─ tree-sitter → extract AST structure
    │   │   │   (imports, exports, function calls, class hierarchy)
    │   │   ├─ CodeSplitter → chunk at function boundaries
    │   │   ├─ Embed → ChromaDB (with content_type metadata)
    │   │   └─ Add code nodes + edges to NetworkX graph
    │   │
    │   ├─ If DOCUMENT (markdown, pdf, docx, txt):
    │   │   ├─ DOCUMENT_BACKEND = "azure"?
    │   │   │   ├─ YES → Azure Doc Intelligence → structured JSON
    │   │   │   │         (tables, fields, layout, paragraphs)
    │   │   │   │         Bypasses LiteParse entirely
    │   │   │   └─ NO  → LiteParse → text/markdown (existing)
    │   │   ├─ metadata_extractor → category + keywords
    │   │   ├─ Embed → ChromaDB (with content_type + category metadata)
    │   │   └─ Mark for document graph (built after all embeddings done)
    │   │
    │   ├─ If CONFIG (yaml, json, toml):
    │   │   └─ Whole-file chunk → ChromaDB
    │   │
    │   └─ If BINARY (executable, image, archive):
    │       └─ SKIP (log skipped count)
    │
    └── AFTER ALL FILES INGESTED:
        │
        ├─ CODE GRAPH (already built during ingestion):
        │   ├─ tree-sitter edges: imports, calls, inheritance
        │   └─ Louvain → code communities
        │
        ├─ DOCUMENT GRAPH (built from existing embeddings):
        │   ├─ Compute pairwise cosine similarity on all doc chunks
        │   ├─ Add edges where similarity > threshold (e.g., 0.85)
        │   ├─ Add edges from shared metadata categories
        │   └─ Louvain → document topic communities
        │
        ├─ CROSS-LINKS (code ↔ documents):
        │   ├─ Match filenames mentioned in document text
        │   └─ Match function/class names in document headings
        │
        ├─ ANALYSIS:
        │   ├─ Identify hub nodes (high in-degree = widely imported)
        │   ├─ Identify bridge nodes (connect separate communities)
        │   └─ Label communities (top files/chunks per cluster)
        │
        └─ CACHE:
            ├─ .opencode/codebase-graph.json (full graph)
            └─ .opencode/magika-inventory.json (file types)
```

### Why Two Strategies?

Code and documents have fundamentally different structures:

| Property | Code | Documents |
|----------|------|-----------|
| Has AST? | ✅ Yes (tree-sitter parses it) | ❌ No |
| Relationships | Explicit (`import X from Y`, `func()`) | Implicit (semantic similarity) |
| Extraction method | tree-sitter (deterministic, no LLM) | Embedding similarity + metadata (no LLM) |
| Graph quality | **Exact** — real imports, real calls | **Approximate** — topical relatedness |
| Index-time LLM cost | **Zero** | **Zero** |

Neither strategy uses an LLM at index time. Code relationships come from 
the AST; document relationships come from existing embeddings and metadata. 
Both are deterministic and fast.

---

## 4. Deployment Modes: Full Local vs Hybrid

The RAG MCP supports two deployment modes. Users choose per-project based 
on their privacy requirements, budget, and document complexity.

### Mode Comparison

```
┌─────────────────────────────────────────────────────────────┐
│  FULL LOCAL (default)                                        │
│                                                              │
│  Everything runs on your machine. No cloud. No network.     │
│                                                              │
│  Document parsing:  LiteParse (Rust + PDFium)                │
│  Embeddings:        qwen3-embedding:0.6b via Ollama          │
│  Code graph:        tree-sitter (local AST)                  │
│  Doc graph:         embedding similarity (local compute)     │
│  Entity extraction: qwen2.5vl:7b via Ollama (optional)       │
│                                                              │
│  ✅ Free  ✅ Private  ✅ Offline  ⚠️ Slower doc parsing        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  HYBRID (Cloud + Local)                                      │
│                                                              │
│  Heavy document parsing in Azure. All key processing local.  │
│                                                              │
│  Document parsing:  Azure Document Intelligence → JSON       │
│                     (bypasses LiteParse, gives tables/fields) │
│  Embeddings:        qwen3-embedding:0.6b via Ollama (LOCAL)  │
│  Code graph:        tree-sitter (LOCAL, always)              │
│  Doc graph:         embedding similarity (LOCAL, always)     │
│  Entity extraction: Azure GPT-4o or qwen2.5vl:7b (optional) │
│                                                              │
│  ✅ Faster docs  ✅ Better tables  ✅ No Mac burden            │
│  ⚠️ Costs money  ⚠️ Data leaves machine  ⚠️ Needs internet     │
└─────────────────────────────────────────────────────────────┘
```

### What Stays Local in Both Modes

These components NEVER go to the cloud, regardless of mode:

| Component | Why it stays local |
|-----------|-------------------|
| Embeddings (qwen3-embedding:0.6b) | Must be in local ChromaDB for vector search |
| Code graph (tree-sitter) | Deterministic AST parsing, no model needed |
| Document similarity graph | Cosine math on local embeddings |
| Louvain community detection | Pure Python, instant |
| Magika file-type detection | Local CLI binary |
| Search/retrieval | Local ChromaDB queries |

### What Changes Between Modes

| Component | Full Local | Hybrid |
|-----------|-----------|--------|
| **PDF/document parsing** | LiteParse → text only | Azure Doc Intelligence → structured JSON with tables, fields, layout |
| **Table extraction** | ❌ Tables flattened to text | ✅ Tables as structured cells with rows/columns/spans |
| **Document chunking** | SentenceSplitter (generic) | Table-aware chunking (tables stay intact) |
| **Optional entity extraction** | qwen2.5vl:7b via Ollama (~30-60s/doc) | Azure GPT-4o (~3-5s/doc) or qwen2.5vl:7b |

### Configuration

```python
# config.py

DOCUMENT_BACKEND = os.getenv("DOCUMENT_BACKEND", "local")
# "local":  LiteParse for document parsing. Free, private, offline.
# "azure":  Azure Document Intelligence for document parsing.
#           Returns structured JSON (tables, fields, layout).
#           Bypasses LiteParse entirely. ~$10/1,000 pages.

# Azure credentials (only needed if DOCUMENT_BACKEND = "azure")
AZURE_DOC_INTELLIGENCE_ENDPOINT = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
AZURE_DOC_INTELLIGENCE_KEY = os.getenv("AZURE_DOC_INTELLIGENCE_KEY", "")
AZURE_DOC_INTELLIGENCE_MODEL = os.getenv("AZURE_DOC_INTELLIGENCE_MODEL", "prebuilt-layout")
```

No Azure credentials configured? Automatic fallback to `local` mode with a 
warning. The system never breaks — it degrades gracefully.

### When to Choose Each Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Sensitive/proprietary codebase | **Full Local** | Documents must not leave your machine |
| Public docs, open-source projects | **Hybrid** | No privacy concern, Azure is faster |
| Complex PDFs with tables/specs | **Hybrid** | Azure extracts table structure LiteParse can't |
| Offline / air-gapped environment | **Full Local** | No internet access |
| Budget-constrained | **Full Local** | Zero cloud cost |
| Large document corpus (500+ docs) | **Hybrid** | Saves hours of Mac CPU time |
| Code-heavy project, few documents | **Full Local** | Documents are simple, Azure adds no value |
| Research papers with figures/charts | **Hybrid** | Azure figure detection + summarisation |

### Azure Document Intelligence Details

For the hybrid mode, Azure Document Intelligence (formerly Form Recognizer) 
is the document parsing backend:

**Prebuilt models available:**

| Model | What it extracts | Use case |
|-------|-----------------|----------|
| `prebuilt-layout` | Text, tables, paragraphs, headings, selection marks, figures | **Default for RAG MCP** — general document structure |
| `prebuilt-read` | OCR text only (simplest, cheapest) | Simple text PDFs |
| `prebuilt-receipt` | Merchant, total, date, line items | Receipt processing (proven in receipt-scanner) |
| `prebuilt-invoice` | Vendor, amounts, due date, line items | Invoice processing |
| `prebuilt-contract` | Parties, clauses, dates, amounts | Contract analysis |
| `prebuilt-idDocument` | Name, DOB, document number, expiry | ID verification |

**Output format**: Structured JSON with:
- Paragraphs with roles (title, section heading, footnote, page header/footer)
- Tables with row/column indices, cell spans, header detection
- Key-value pairs with confidence scores
- Selection marks (checkboxes)
- Bounding boxes for every element
- Figure/chart detection with optional summarisation

**Pricing**: ~$10 per 1,000 pages (prebuilt models). Free tier: 500 pages/month.
Compliance: SOC 2, HIPAA, PCI, FedRAMP. Data not used for model training.

**Also available (preview)**: Azure Content Understanding — adds semantic 
reasoning, multimodal processing (images/audio/video), figure summarisation, 
section classification. Still in preview; evaluate when GA.

---

## 5. Code Graph: tree-sitter + NetworkX

### What tree-sitter Extracts

For each code file, tree-sitter parses the AST and extracts:

| Relationship type | Example (TypeScript) | Graph edge |
|-------------------|----------------------|------------|
| Import | `import { Auth } from './auth'` | `login.ts → auth.ts` |
| Export | `export class UserService` | `UserService defined in user.ts` |
| Function call | `auth.validate(token)` | `login.ts → auth.ts::validate` |
| Class inheritance | `class Admin extends User` | `Admin → User` |
| Type reference | `function get(x: Request)` | `handler.ts → types.ts::Request` |

Supported languages: TypeScript, JavaScript, Python, PHP, Go, Rust, Ruby, 
Java, C, C++, Shell, and 40+ more via `tree-sitter-language-pack`.

### Community Detection

Run Louvain algorithm on the NetworkX graph to cluster related files:

```
Code Communities:
  "Auth & Session" — login.ts, session.ts, middleware.ts, redis.ts (8 files)
  "Receipt OCR" — scan.ts, preprocess.ts, ollama.ts, parse.ts (12 files)
  "API Routing" — router.ts, routes/*.ts, inertia.ts (5 files)
```

NetworkX's built-in `louvain_communities()` is sufficient — no need for 
`graspologic` (which adds heavy scipy/scikit-learn dependencies).

### Hub Detection

Identify files imported by many others (high in-degree):

```
Key hubs:
  src/config/database.ts — imported by 14 files
  src/utils/helpers.ts — imported by 11 files
  src/types/index.ts — imported by 9 files
```

These are architectural landmarks — the agent should know about them upfront.

---

## 6. Document Graph: Embedding Similarity + Metadata

### Why Not tree-sitter for Documents?

Documents (PDFs, markdown, Word docs) have no AST. You can't parse 
"relationships" from document syntax the way you can from code. Instead, 
we build a graph from two signals that already exist in the RAG MCP:

### Signal 1: Embedding Similarity

After all documents are embedded (existing pipeline), compute pairwise cosine 
similarity between document chunks. Draw edges where similarity exceeds a 
threshold:

```
api-guide.md chunk 3 ("authentication flow")
  ├── 0.91 → auth-api.md chunk 1 ("login endpoint")
  ├── 0.87 → security.md chunk 2 ("session tokens")  
  └── 0.85 → deployment.md chunk 4 ("auth in production")
```

**Cost**: Zero new LLM calls. The embeddings already exist in ChromaDB. 
For 500 chunks, cosine similarity computation takes seconds. We only 
compute within-document-type pairs to keep it efficient.

### Signal 2: Metadata Categories

The existing `metadata_extractor` assigns `category` (normalised, ADR-013) 
and `keywords` (3-5 per chunk) to every document chunk. Build edges from 
shared categories:

```
All chunks with category="security" → connected
All chunks with category="deployment" → connected
Shared keywords ("redis", "session") → weak edge
```

### Signal 3: Document Structure

For markdown files, `MarkdownNodeParser` already captures heading hierarchy. 
In hybrid mode, Azure Document Intelligence provides richer structure 
(paragraphs with roles, section detection, figure boundaries). Build 
parent-child edges from whichever parser was used:

```
README.md (or Azure layout JSON)
├─ "# Installation" → chunk 1
├─ "# API" → chunk 2
│   ├─ "## Authentication" → chunk 3
│   └─ "## Rate Limiting" → chunk 4
└─ "# Configuration" → chunk 5

Edges: chunk 2 → chunk 3, chunk 2 → chunk 4
```

### Document Communities

Run Louvain on the combined document graph:

```
Document Communities:
  "API Reference" — api-guide.md, auth-api.md, webhook-api.md (23 chunks)
  "Deployment" — docker-setup.md, ci-cd.md, kubernetes.md (15 chunks)
  "Architecture Decisions" — adr-001.md to adr-021.md (21 chunks)
```

---

## 7. Cross-Links: Code ↔ Documents

The final piece connects code communities to document communities:

| Detection method | Example | How |
|-----------------|---------|-----|
| Filename match | `auth/login.ts` ↔ `api-guide.md` mentions "auth/login" | Scan document text for code file paths |
| Symbol match | `UserService` class ↔ doc heading "UserService" | Scan document headings for exported symbols |
| Category match | Code community "Auth" ↔ Doc community "API Reference" (both mention auth) | Compare community keyword overlap |

These cross-links let the agent answer: "where is the auth module 
documented?" without searching.

---

## 8. The Output: `get_codebase_map`

One MCP tool returns the full codebase map — file types, code communities, 
document communities, cross-links, hubs:

```
## Codebase Map

### File Types (Magika)
code/typescript: 47 files (src/**/*.ts)
code/python: 12 files (scripts/**/*.py)
config/yaml: 5 files (.github/workflows/*)
document/markdown: 8 files (docs/**)
⚠ BINARY: bin/migrate (ELF) — DO NOT READ
⚠ MISMATCH: utils.txt → detected as JavaScript

### Code Communities (tree-sitter + Louvain)
1. "Auth & Session" (8 files, 23 edges)
   login.ts, session.ts, middleware.ts, redis.ts
   Hub: src/auth/session.ts (imported by 6 files)
2. "Receipt OCR Pipeline" (12 files, 41 edges)
   scan.ts, preprocess.ts, ollama.ts, parse.ts
   Hub: src/ocr/parser.ts (imported by 8 files)
3. "API Routing" (5 files, 15 edges)
   router.ts, routes/*.ts, inertia.ts

### Document Communities (embedding similarity + metadata)
1. "API Reference" (23 chunks, 4 documents)
2. "Deployment & Infrastructure" (15 chunks, 3 documents)
3. "Architecture Decisions" (21 chunks, category=adr)

### Cross-links
- auth/login.ts ↔ api-guide.md#authentication
- ocr/parser.ts ↔ receipt-scanning-guide.md

### Architectural Hubs (imported by many)
- src/config/database.ts (14 importers)
- src/utils/helpers.ts (11 importers)
```

Target: ~500-800 tokens total. Compact enough for system prompt injection, 
rich enough for the agent to skip 10+ exploratory tool calls.

---

## 9. Existing RAG MCP: What Changes

### Current State (v1.7.0)

- Embeddings: `qwen3-embedding:0.6b` via Ollama (1024-dim)
- Chunking: `SentenceSplitter(512, 100)`; `MarkdownNodeParser` for `.md`
- PDF reader: LiteParse (primary) → pypdfium2 → pypdf (fallback chain, ADR-020)
- Storage: ChromaDB PersistentClient
- Search: Dense + optional Hybrid + optional Reranker (disabled by default)
- Watcher: watchdog + SHA-256 dedup
- Tools: `ingest_documents`, `search_documents`, `list_indexed_documents`, 
  `list_collections`, `delete_documents`

### New Files

```
src/rag_mcp/
├── codebase_map.py       ← NEW: Magika scan + graph assembly + inventory compaction
├── code_graph.py         ← NEW: tree-sitter extraction + NetworkX graph
├── doc_graph.py          ← NEW: embedding similarity + metadata graph
├── azure_reader.py       ← NEW: Azure Doc Intelligence integration (hybrid mode only)
├── ingestion.py          ← MODIFY: type-aware chunking dispatch + Azure/LiteParse branch
├── config.py             ← MODIFY: add MAGIKA_BINARY, DOCUMENT_BACKEND, graph thresholds
├── server.py             ← MODIFY: add get_codebase_map MCP tool
├── retrieval.py          ← Unchanged
├── metadata_extractor.py ← Unchanged
├── chroma_utils.py       ← Unchanged
└── reranker.py           ← Unchanged
```

### Modified: Type-Aware Ingestion

One function changes in `ingestion.py:_read_and_chunk_file_async()`:

| Magika content_type | Chunking | Graph action |
|---------------------|----------|-------------|
| `code/*` | `CodeSplitter` (tree-sitter boundaries) | Extract AST → add to code graph |
| `markdown` | `MarkdownNodeParser + SentenceSplitter(1024)` (existing) | Add heading hierarchy edges |
| `config/yaml/json/toml` | Whole-file chunks | None |
| `document/pdf/docx/txt` | `DOCUMENT_BACKEND="azure"`: Azure JSON → table-aware chunks<br>`DOCUMENT_BACKEND="local"`: LiteParse → SentenceSplitter | Mark for doc graph |
| `executable/*`, `image/*` | SKIP | Log as binary |

### Modified: PDF Reader Chain (ADR-020 extension)

Current chain: `LiteParse → pypdfium2 → pypdf`

Extended chain with hybrid mode:

```
DOCUMENT_BACKEND = "azure":
    Azure Doc Intelligence → structured JSON (tables, fields, layout)
    └─ Bypasses LiteParse entirely
    └─ If Azure fails (network/rate limit): fall back to LiteParse chain

DOCUMENT_BACKEND = "local":
    LiteParse → pypdfium2 → pypdf  (existing chain, unchanged)
```

### New MCP Tool

```python
@mcp.tool()
async def get_codebase_map(
    path: str = ".",
    refresh: bool = False
) -> str:
    """Return compact codebase map for agent fast context.
    
    Includes: file types (Magika), code communities (tree-sitter + Louvain),
    document communities (embedding similarity), cross-links, and hubs.
    
    Cached per-project, invalidated by git commit.
    """
```

### New Dependencies

| Package | Purpose | Required for | Size |
|---------|---------|-------------|------|
| `tree-sitter` | AST parsing engine | Both modes | Light (C extension) |
| `tree-sitter-language-pack` | Language grammars (50+) | Both modes | Medium |
| `networkx` | Graph + Louvain community detection | Both modes | Light (pure Python) |
| `magika` (CLI) | File-type detection | Both modes | System (`brew install`) |
| `azure-ai-documentintelligence` | Azure Doc Intelligence SDK | Hybrid mode only | Light |

No `graspologic`. No `scipy`. The Azure SDK is an optional dependency — 
only installed when `DOCUMENT_BACKEND = "azure"`.

---

## 10. OpenCode Plugin (Thin Wrapper)

A thin OpenCode plugin calls `get_codebase_map` at session start and injects 
the result into the system prompt:

```typescript
// .opencode/plugins/fast-context.ts
export const FastContextPlugin: Plugin = async ({ }) => {
  const injected = new Set<string>()
  return {
    "experimental.chat.system.transform": async (input, output) => {
      if (input.sessionID && injected.has(input.sessionID)) return
      const map = await callRagMcp("get_codebase_map", { path: "." })
      output.system.push(map)
      injected.add(input.sessionID)
    }
  }
}
```

The plugin does NO processing — all logic lives in the RAG MCP. If the plugin 
is missing, agents can call `get_codebase_map` directly via MCP.

---

## 11. Implementation Phases

### Phase 1: Magika + Inventory (~1 week)

**Goal**: File-type inventory working.

1. `brew install magika` (system dependency)
2. New file: `codebase_map.py` — Magika scan, JSONL parse, compact inventory
3. Cache to `.opencode/magika-inventory.json` keyed by `git rev-parse HEAD`
4. New MCP tool: `get_codebase_map(path, refresh)` — returns inventory only
5. Graceful degradation: if Magika missing, fall back to extension detection

### Phase 2: Code Graph (~1 week)

**Goal**: tree-sitter extraction + code communities.

1. New file: `code_graph.py`
2. Add `tree-sitter` + `tree-sitter-language-pack` + `networkx` dependencies
3. During ingestion, for code files: extract imports/calls/classes → NetworkX
4. After ingestion: run `louvain_communities()`, detect hubs
5. Extend `get_codebase_map` to include code communities + hubs
6. Write ADR: "Code graph via tree-sitter AST extraction"
7. Experiment: verify community detection quality on the RAG MCP's own codebase

### Phase 3: Document Graph (~3-5 days)

**Goal**: Document communities from embeddings + metadata.

1. New file: `doc_graph.py`
2. After all document chunks are embedded, compute pairwise cosine similarity
3. Build edges: similarity > threshold, shared categories, heading hierarchy
4. Run Louvain → document communities
5. Add cross-links: filename/symbol matching between code and docs
6. Extend `get_codebase_map` to include document communities + cross-links
7. Experiment: verify document communities are semantically coherent

### Phase 4: Type-Aware Ingestion (~2-3 days)

**Goal**: Code files get `CodeSplitter`, binaries get skipped.

1. Modify `ingestion.py:_read_and_chunk_file_async()`: accept content type
2. Dispatch to `CodeSplitter` for code, skip binaries
3. Add `content_type` to ChromaDB metadata
4. Enable `metadata_filter` in `search_documents`
5. Experiment: compare retrieval quality (type-aware vs generic chunking)

### Phase 5: OpenCode Plugin (~1 day)

**Goal**: Automatic injection into agent system prompt.

1. Write `.opencode/plugins/fast-context.ts`
2. Calls `get_codebase_map`, injects into `experimental.chat.system.transform`
3. Per-session caching (fetch once per session)
4. Test with `a-explore` and `a-deep-search` agents

### Phase 6: Azure Document Intelligence (Hybrid Mode) (~3-5 days)

**Goal**: Optional cloud document parsing for better table/structure extraction.

1. New file: `azure_reader.py` — Azure Doc Intelligence SDK integration
2. Add `DOCUMENT_BACKEND` config + `AZURE_DOC_INTELLIGENCE_*` env vars
3. In `ingestion.py`: branch on `DOCUMENT_BACKEND` for document files
4. Parse Azure JSON: table-aware chunking (tables stay intact as chunks)
5. Store `content_type: "table"` metadata for table chunks
6. Graceful fallback: if Azure fails or not configured → LiteParse chain
7. Port Azure client pattern from receipt-scanner project (proven integration)
8. Experiment: compare Azure table extraction vs LiteParse on complex PDFs

**Independent of Phases 1-5.** Can be built in parallel.

### Future: Optional LLM-Based Document Entity Extraction

The embedding similarity + metadata graph (Phase 3) answers "which documents 
are related?" by clustering topically similar chunks. But it cannot answer 
"what entities are mentioned in this document and how do they relate?" — 
questions like "Person X authored Paper Y which cites Paper Z" or "this 
contract references Clause 4.2 of the Terms of Service."

When (and only when) that level of semantic entity extraction is needed, 
three options exist across both deployment modes.

#### Option A: On-Demand Extraction with `qwen2.5vl:7b` (Local) — Recommended

**How it works**: The agent explicitly asks for entity extraction via a new 
MCP tool. The LLM runs only when queried, not during ingestion.

```python
@mcp.tool()
async def extract_entities(
    query: str,
    collection: str = "documents",
    top_k: int = 10
) -> str:
    """Extract entities and relationships from documents relevant to a query.
    
    Uses qwen2.5vl:7b via Ollama for structured JSON extraction.
    Only runs when explicitly called — not during ingestion.
    
    Returns:
        JSON with entities[], relationships[], confidence scores
    """
    # 1. RAG retrieves relevant chunks (existing pipeline)
    # 2. qwen2.5vl:7b extracts entities/relationships from those chunks
    # 3. Return structured JSON
```

**Why `qwen2.5vl:7b`**: This model is already proven in the receipt-scanner 
project (`/Users/aizat/Development/PROJECTS/receipt-scanner-tracker`) for 
extracting structured JSON from visual input (receipt photos). For document 
text extraction, it runs on text only (no vision needed) but benefits from 
the same proven JSON-output reliability. It handles structured output far 
better than `qwen3:0.6b`, which is an embedding model — not designed for 
generation tasks.

**Model selection rationale**:

| Model | Role in this system | Why not use for entity extraction? |
|-------|--------------------|------------------------------------|
| `qwen3-embedding:0.6b` | RAG embeddings (all phases) | Embedding model, not a generator. Cannot produce structured output. Correct tool for vector similarity, wrong tool for entity extraction. |
| `qwen2.5vl:7b` | Entity extraction (this option) | Proven JSON output in receipt-scanner OCR. 7B parameters give enough reasoning for entity/relationship extraction without cloud cost. Vision-capable (can handle image-based PDFs if needed). |

**Cost**: Per-query, not per-index. Only fires when the agent explicitly asks 
"what are the key entities in these documents?" Typical: 1-2 LLM calls per 
query. On Ollama, ~2-5 seconds per call.

**Best for**: Ad-hoc questions about document relationships. Works in both 
Full Local and Hybrid modes.

#### Option B: LlamaIndex KnowledgeGraphIndex at Index Time

**How it works**: During ingestion, LlamaIndex's `KnowledgeGraphIndex` passes 
each chunk to an LLM that extracts (subject, predicate, object) triplets. 
These triplets become graph edges.

**LLM choices**:
- **Local mode**: `qwen2.5vl:7b` via Ollama (~500 calls for 500 chunks, ~20-40 min)
- **Hybrid mode**: Azure OpenAI GPT-4o (~500 calls, ~5-10 min, higher quality, 
  stable JSON)

**Cost**: One LLM call per chunk at index time. In hybrid mode with GPT-4o, 
~$1-5 total for 500 chunks. In local mode with qwen2.5vl:7b, free but slow.

**Risk**: Small local models (7B) sometimes produce malformed triplets. 
Needs a validation step. GPT-4o in hybrid mode avoids this.

**Best for**: When you need a persistent entity-relationship graph that 
supports graph traversal queries without re-running the LLM each time.

#### Option C: LightRAG with Ollama or Azure

**How it works**: LightRAG (EMNLP 2025) is a lightweight GraphRAG alternative 
that achieves 70-90% of Microsoft GraphRAG's quality at 1/100th the cost.

**Cost**: Lighter than full GraphRAG, but still requires LLM-based entity 
extraction per chunk. Supports both Ollama (local) and Azure OpenAI (hybrid).

**Best for**: Global thematic reasoning over a large document corpus.

#### Decision Matrix

| Criterion | Option A (On-demand) | Option B (KGIndex at index) | Option C (LightRAG) |
|-----------|---------------------|-----------------------------|---------------------|
| **When LLM runs** | Query time (on-demand) | Index time | Index time |
| **Local mode LLM** | qwen2.5vl:7b (~2-5s) | qwen2.5vl:7b (~20-40 min) | qwen2.5vl:7b |
| **Hybrid mode LLM** | qwen2.5vl:7b (still local) | Azure GPT-4o (~5-10 min) | Azure GPT-4o |
| **Index cost** | Zero (uses Phase 3 graph) | ~500 LLM calls | ~100-200 calls |
| **Query cost** | 1-2 LLM calls per query | Zero (pre-built) | Low (traversal) |
| **JSON stability** | Low risk (proven model) | Medium (local) / Low (Azure) | Medium |
| **Best for** | Ad-hoc entity questions | Stable corpus, frequent queries | Global thematic reasoning |
| **Recommendation** | ⭐ **Start here** | If A proves insufficient | If B proves insufficient |

#### Recommendation

**Start with Option A** (on-demand `qwen2.5vl:7b`). It adds zero indexing 
cost and only fires when the agent explicitly asks. Works in both modes.

If the agent frequently asks entity questions, **graduate to Option B**. In 
hybrid mode, use Azure GPT-4o for fast, stable triplet extraction. In local 
mode, use qwen2.5vl:7b with a validation step.

**Option C (LightRAG)** is the fallback if neither A nor B provides 
sufficient quality.

---

## 12. Cost Analysis

### Full Local Mode — One-Time Setup (500-file codebase)

| Step | Time | LLM tokens | Cost |
|------|------|-----------|------|
| `brew install magika` | ~30 sec | 0 | Free |
| Magika scan | ~2-3 sec | 0 | Free |
| tree-sitter extraction | ~1-2 sec | 0 | Free |
| Embedding similarity graph | ~2-3 sec | 0 | Free |
| Louvain (code + doc graphs) | <1 sec | 0 | Free |
| RAG ingestion (embeddings) | ~13 min | 0 | Free |
| **Total** | **~14 min** | **0** | **Free** |

### Hybrid Mode — One-Time Setup (500-file codebase, 50 PDFs)

| Step | Time | LLM tokens | Cost |
|------|------|-----------|------|
| Magika scan | ~2-3 sec | 0 | Free |
| tree-sitter extraction | ~1-2 sec | 0 | Free |
| Azure Doc Intelligence (50 PDFs) | ~3-5 min | 0 (API, not LLM) | ~$0.50 |
| Embedding similarity graph | ~2-3 sec | 0 | Free |
| Louvain | <1 sec | 0 | Free |
| RAG ingestion (embeddings) | ~13 min | 0 | Free |
| **Total** | **~17 min** | **0** | **~$0.50** |

### Per-Session (Both Modes)

| Component | Cost | Frequency |
|-----------|------|-----------|
| Codebase map in system prompt | ~500-800 tokens | Every message |
| RAG query | ~104ms + result tokens | On-demand |

### Incremental (per git commit)

| Component | Full Local | Hybrid |
|-----------|-----------|--------|
| Magika re-scan | ~2-3 sec (free) | ~2-3 sec (free) |
| tree-sitter re-extraction | ~1-2 sec (free) | ~1-2 sec (free) |
| Document re-parsing | LiteParse (free) | Azure (~$0.01/changed PDF) |
| Embedding similarity recompute | ~2-3 sec (free) | ~2-3 sec (free) |
| RAG re-ingestion | Per-file (free) | Per-file (free) |

---

## 13. Technical Decisions

### D1: tree-sitter for code, embeddings for documents

**Decision**: Use deterministic AST extraction for code files (tree-sitter), 
and embedding similarity + metadata for documents. Neither uses LLM at index 
time.

**Rationale**: Code has explicit relationships (imports, calls, inheritance) 
that tree-sitter extracts perfectly. Documents have only implicit relationships 
(topical similarity) which embeddings capture without LLM.

### D2: NetworkX Louvain over graspologic Leiden

**Decision**: Use NetworkX's built-in `louvain_communities()`.

**Rationale**: graspologic adds heavy scipy/scikit-learn dependencies. For 
codebase-scale graphs, Louvain is sufficient and keeps deps light.

### D3: Magika as CLI dependency, not Python package

**Decision**: Shell out to `magika` CLI (`brew install magika`).

**Rationale**: Faster, no Python dependency conflicts, Homebrew bottled. 
Graceful degradation if missing.

### D4: Per-project cache keyed by git commit

**Decision**: Cache at `<project>/.opencode/`, invalidated by 
`git rev-parse HEAD`.

**Rationale**: Simple, deterministic. Files change when commits happen.

### D5: Thin OpenCode plugin, all logic in RAG MCP

**Decision**: The OpenCode plugin does nothing except call `get_codebase_map` 
and inject the result.

**Rationale**: All Python logic stays in the RAG MCP. If the plugin breaks, 
agents call the MCP tool directly.

### D6: No LLM-based entity extraction at index time (default)

**Decision**: Do not use LLM to extract entities/relationships during 
ingestion by default. Defer to query time (on-demand).

**Rationale**: LLM extraction is expensive and risks JSON instability. 
tree-sitter gives exact code relationships. Embedding similarity gives 
approximate document relationships. Both are free.

### D7: `qwen2.5vl:7b` for optional entity extraction, not `qwen3:0.6b`

**Decision**: If LLM-based document entity extraction is needed in local 
mode, use `qwen2.5vl:7b`, not `qwen3-embedding:0.6b`.

**Rationale**: `qwen3:0.6b` is an embedding model — it produces vectors, not 
text. It cannot generate JSON. `qwen2.5vl:7b` is a generation model proven 
for structured JSON in the receipt-scanner project.

### D8: Configurable deployment mode (Full Local vs Hybrid)

**Decision**: Support both Full Local and Hybrid (Azure + Local) deployment 
modes via a single config flag: `DOCUMENT_BACKEND = "local" | "azure"`.

**Rationale**: Different projects have different constraints:
- **Sensitive/proprietary projects** need Full Local — documents must not 
  leave the machine
- **Public/complex-document projects** benefit from Hybrid — Azure gives 
  better table/layout extraction, faster, no Mac burden
- The user already has Azure Document Intelligence integrated and proven in 
  the receipt-scanner project

The hybrid mode follows the existing fallback-chain pattern (ADR-020): 
Azure Doc Intelligence → LiteParse → pypdfium2 → pypdf. If Azure fails or 
isn't configured, the system degrades to local automatically.

**What stays local in both modes**: embeddings (qwen3-embedding:0.6b), code 
graph (tree-sitter), document similarity graph (cosine on embeddings), 
Louvain clustering, Magika detection, ChromaDB search. These components 
never touch the cloud.

---

## 14. Risks & Mitigations

| Risk | Severity | Mode | Mitigation |
|------|----------|------|------------|
| Magika not installed | 🟡 Medium | Both | Graceful degradation to extension detection |
| tree-sitter grammar missing | 🟢 Low | Both | Fall back to SentenceSplitter |
| Document communities incoherent | 🟡 Medium | Both | Experiment in Phase 3; tune threshold |
| System prompt bloat | 🟡 Medium | Both | Cap at ~800 tokens; counts + globs |
| `experimental.chat.system.transform` changes | 🟢 Low | Both | Plugin is thin; agent calls MCP directly |
| Azure unavailable / network down | 🟡 Medium | Hybrid | Automatic fallback to LiteParse chain |
| Azure cost accumulation | 🟢 Low | Hybrid | Incremental indexing (changed files only); free tier 500 pages/month |
| Document data leaves machine (privacy) | 🟡 Medium | Hybrid | Config flag per-project; sensitive projects use Full Local |
| Azure SDK adds dependency | 🟢 Low | Hybrid | Optional install; only when `DOCUMENT_BACKEND = "azure"` |

---

## 15. Open Questions

1. **Similarity threshold for document graph**: 0.85? 0.80? Needs tuning 
   based on qwen3-embedding:0.6b. Experiment in Phase 3.

2. **tree-sitter relationship depth**: Imports only? Or also calls and type 
   references? Start with imports + class inheritance, add calls if needed.

3. **Community labelling**: How to generate human-readable labels? Options: 
   (a) top file names, (b) shared keywords, (c) LLM summary. Start with (a)+(b).

4. **Cross-link false positives**: Filename matching in docs may produce 
   noise ("config" mentioned generically). Needs validation in Phase 3.

5. **Monorepo handling**: Communities per-workspace or across monorepo?

6. **Azure table-aware chunking**: When Azure returns a table as structured 
   JSON, how should it be chunked? Whole table as one chunk? Row groups? 
   Needs experiment in Phase 6.

7. **Azure Content Understanding GA timeline**: The newer multimodal service 
   (figure summarisation, section classification) is still in preview. 
   Evaluate when GA for richer document structure extraction.

---

## 16. Success Metrics

- **Exploration call reduction**: 50%+ fewer `ls`/`glob`/`read_file` calls
- **First-action relevance**: Agent's first action reflects codebase awareness
- **Community coherence**: Code communities = actual modules; doc communities 
  = actual topics (validated by manual review)
- **Indexing cost (Full Local)**: First-time setup < 15 minutes, zero cost
- **Indexing cost (Hybrid)**: First-time setup < 20 minutes, < $1 for 50 PDFs
- **Incremental cost**: Re-index after single-file change < 30 seconds
- **Table extraction quality (Hybrid)**: Azure-extracted tables retrievable 
  as structured chunks, not flattened text

---

## Appendix A: File Changes Summary

```
src/rag_mcp/
├── codebase_map.py          ← NEW: Magika + graph assembly + inventory
├── code_graph.py            ← NEW: tree-sitter AST extraction → NetworkX
├── doc_graph.py             ← NEW: embedding similarity → NetworkX
├── azure_reader.py          ← NEW: Azure Doc Intelligence (hybrid only)
├── ingestion.py             ← MODIFY: type-aware dispatch + Azure/LiteParse branch
├── config.py                ← MODIFY: DOCUMENT_BACKEND, MAGIKA_BINARY, graph config
├── server.py                ← MODIFY: add get_codebase_map tool
├── retrieval.py             ← Unchanged
├── metadata_extractor.py    ← Unchanged
├── chroma_utils.py          ← Unchanged
└── reranker.py              ← Unchanged

.opencode/plugins/
└── fast-context.ts          ← NEW: thin plugin, calls get_codebase_map

Dependencies (both modes):
├── tree-sitter              ← pip
├── tree-sitter-language-pack← pip
├── networkx                 ← pip
└── magika                   ← brew install (system)

Dependencies (hybrid mode only):
└── azure-ai-documentintelligence ← pip (optional)
```

## Appendix B: Graph Data Structures

### Code Graph (NetworkX DiGraph)

```python
graph.add_node("src/auth/login.ts", 
    type="file", content_type="code/typescript",
    functions=["handleLogin", "validateCredentials"],
    imports=["src/auth/session.ts", "src/utils/helpers.ts"]
)
graph.add_edge("src/auth/login.ts", "src/auth/session.ts", 
    relation="import", confidence="exact")
```

### Document Graph (NetworkX Graph)

```python
graph.add_node("chunk_42",
    type="document_chunk", file_path="docs/api-guide.md",
    heading="Authentication", category="api",
    keywords=["auth", "login", "token"]
)
graph.add_edge("chunk_42", "chunk_87",
    relation="similar", weight=0.91)
```

## Appendix C: Deployment Mode Config

### Full Local (default)

```bash
# .env — no Azure credentials needed
DOCUMENT_BACKEND=local
OLLAMA_BASE_URL=http://localhost:11434
EMBED_MODEL=qwen3-embedding:0.6b
```

### Hybrid (Azure + Local)

```bash
# .env — Azure credentials for document parsing
DOCUMENT_BACKEND=azure
AZURE_DOC_INTELLIGENCE_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
AZURE_DOC_INTELLIGENCE_KEY=<key>
AZURE_DOC_INTELLIGENCE_MODEL=prebuilt-layout

# Local processing still uses Ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBED_MODEL=qwen3-embedding:0.6b
```

### Graceful Fallback

If `DOCUMENT_BACKEND=azure` but credentials are missing or Azure is 
unreachable, the system automatically falls back to LiteParse with a 
warning. No data loss, no crash.

## Appendix D: Magika JSONL Output

Each line of `magika -r . --jsonl`:

```json
{
  "path": "./src/index.ts",
  "result": {
    "status": "ok",
    "value": {
      "output": {
        "label": "typescript",
        "group": "code",
        "is_text": true,
        "mime_type": "text/typescript"
      },
      "score": 0.997
    }
  }
}
```

Key fields: `path`, `output.group` (code/config/document/executable), 
`output.label`, `output.is_text`, `output.score`.

---

*Generated by a-tech-researcher research session, 2026-06-26. British English throughout.*
