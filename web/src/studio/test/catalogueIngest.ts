/* Ingestion operations from the real operation catalogue (`build_operation_catalogue().describe(...)`), captured 2026-10-17.
 * Kept out of `CATALOGUE` so the palette and graph tests do not change. */
import type { OperationDescriptor } from "../../api/pipelines";

export const CATALOGUE_INGEST: OperationDescriptor[] = [
 {
  "operation_id": "embed.chunks",
  "version": 1,
  "title": "Embed chunks",
  "family": "embed",
  "description": "Stamp chunk lineage and embed with the host embedder. Malformed vectors fail here, before any write.",
  "parameters": {
   "additionalProperties": false,
   "description": "Operation without parameters.",
   "properties": {},
   "title": "NoParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "chunks",
    "type": {
     "kind": "chunks",
     "provenance": [
      "source"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Chunks of one source."
   }
  ],
  "outputs": [
   {
    "name": "chunks",
    "type": {
     "kind": "embedded_chunks",
     "provenance": [
      "chunk_lineage",
      "source"
     ],
     "score_kinds": null,
     "embedding_identity": true,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Chunks with lineage and vectors."
   }
  ],
  "capabilities": [
   "embedder"
  ],
  "effect": "model_call",
  "bypass": null,
  "collection_param": null,
  "lever_params": {},
  "free_text_params": [],
  "index_shaping": true,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "prepare.chunk",
  "version": 1,
  "title": "Split into chunks",
  "family": "prepare",
  "description": "Split documents with the registered strategy. Reader-declared Markdown uses the Markdown splitter.",
  "parameters": {
   "additionalProperties": false,
   "description": "Node overrides for ``prepare.chunk`` (``None`` inherits).\n\nAttributes:\n    chunk_size: ``chunking.chunk_size`` lever.\n    chunk_overlap: ``chunking.chunk_overlap`` lever.\n    markdown_chunk_size: ``chunking.markdown_chunk_size`` lever.",
   "properties": {
    "chunk_size": {
     "anyOf": [
      {
       "minimum": 1,
       "type": "integer"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Chunk Size"
    },
    "chunk_overlap": {
     "anyOf": [
      {
       "minimum": 0,
       "type": "integer"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Chunk Overlap"
    },
    "markdown_chunk_size": {
     "anyOf": [
      {
       "minimum": 1,
       "type": "integer"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Markdown Chunk Size"
    }
   },
   "title": "ChunkParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "documents",
    "type": {
     "kind": "documents",
     "provenance": [
      "source"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": [
      "structured",
      "text_format"
     ]
    },
    "cardinality": "one",
    "description": "Documents to split."
   }
  ],
  "outputs": [
   {
    "name": "chunks",
    "type": {
     "kind": "chunks",
     "provenance": [
      "source"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Chunks of one source."
   }
  ],
  "capabilities": [],
  "effect": "pure",
  "bypass": null,
  "collection_param": null,
  "lever_params": {
   "chunk_size": "chunking.chunk_size",
   "chunk_overlap": "chunking.chunk_overlap",
   "markdown_chunk_size": "chunking.markdown_chunk_size"
  },
  "free_text_params": [],
  "index_shaping": true,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "source.discover",
  "version": 1,
  "title": "Discover sources",
  "family": "sources",
  "description": "List the eligible files under a path with their detected content types. Run the downstream nodes once per listed source.",
  "parameters": {
   "additionalProperties": false,
   "description": "Operation without parameters.",
   "properties": {},
   "title": "NoParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "sources",
    "type": {
     "kind": "sources",
     "provenance": [],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "File or directory path."
   }
  ],
  "outputs": [
   {
    "name": "sources",
    "type": {
     "kind": "sources",
     "provenance": [
      "source"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Source units in discovery order."
   }
  ],
  "capabilities": [],
  "effect": "read_only",
  "bypass": null,
  "collection_param": null,
  "lever_params": {},
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 }
];
