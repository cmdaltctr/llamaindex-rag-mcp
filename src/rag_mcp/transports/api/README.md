# REST API Transport — Contract First, Implementation Later

This directory contains the **OpenAPI 3.1 contract** for the future REST
transport of the RAG MCP server. It ships as a versioned document
**before** any HTTP runtime code. The REST implementation is a separate
follow-up OpenSpec change.

## What's Here

| File | Purpose |
|------|---------|
| `openapi.yaml` | OpenAPI 3.1 contract — the HTTP shape's source of truth |
| `README.md` | This file — design rationale and implementation boundary |

**No `.py` files.** The folder contains zero runtime HTTP code.

## Design Principles

1. **Contract-first.** The OpenAPI document is reviewed as a document,
   mapped to existing core operations, and validated in CI — before any
   FastAPI (or equivalent) code is written.
2. **Shared core, separate transports.** MCP, CLI, and REST all call the
   same `core/` operations. MCP does **not** generate REST routes from
   tool signatures. The OpenAPI document is the HTTP shape's source of
   truth, not a derivative of the MCP tool schemas.
3. **Error envelope alignment.** The REST error response matches the MCP
   error-dict shape (`{"status": "error", "message": "..."}`) so clients
   can reuse error-handling logic across transports.
4. **Destructive operations carry a preview/confirm contract.** Profile
   changes and deletions require a preview call before mutation, matching
   the MCP safety contract.

## Core Operation Mapping

| Core operation | MCP tool | REST endpoint |
|---|---|---|
| Ingest path | `ingest_documents` | `POST /v1/ingestions` |
| Search collection | `search_documents` | `POST /v1/collections/{collection}/search` |
| List documents | `list_indexed_documents` | `GET /v1/collections/{collection}/documents` |
| List collections | `list_collections` | `GET /v1/collections` |
| Delete documents | `delete_documents` | `DELETE /v1/collections/{collection}/documents` |
| Generate codebase map | `get_codebase_map` | `POST /v1/codebase-maps` |
| Change collection profile | `change_collection_profile` | `PATCH /v1/collections/{collection}/profile` |

## Long-Running Operations

`POST /v1/ingestions` and `POST /v1/codebase-maps` may exceed a
synchronous response window. The contract declares them **asynchronous**:

- **202 Accepted** with a job-resource schema (job ID + status)
- Polling via `GET /v1/jobs/{jobId}`
- Terminal states: `completed`, `failed`

## Authentication

The contract declares a `bearerAuth` security scheme (API key or JWT).
Every operation references it. The implementation will resolve the
specific token type when the REST transport is built.

## Implementation Boundary

When the REST implementation lands (separate OpenSpec change):

1. **Reconcile the contract with typed core models first.** Pydantic
   request/result models define Python-level validation; the OpenAPI
   document defines the public HTTP shape. The follow-up change must
   verify they stay aligned.
2. **FastAPI (or equivalent) translates HTTP → core operations.** No
   business logic in the transport layer.
3. **CI validation must keep passing.** The OpenAPI validation step
   added in this phase runs on every push.
