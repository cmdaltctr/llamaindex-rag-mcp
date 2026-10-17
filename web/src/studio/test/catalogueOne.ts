/* Subset of the real operation catalogue (`build_operation_catalogue().describe(...)`), captured 2026-10-13. Part 1 of 2: combine, context, prepare, retrieve (dense, query). */
import type { OperationDescriptor } from "../../api/pipelines";

export const CATALOGUE_PART_ONE: OperationDescriptor[] = [
 {
  "operation_id": "combine.rrf",
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
  "version": 1,
  "title": "Reciprocal rank fusion",
  "family": "combine",
  "description": "Fuse one dense and one sparse ranking.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "rrf_k": {
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
     "title": "Rrf K"
    }
   },
   "title": "RrfParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "ranked",
    "type": {
     "kind": "ranked_evidence",
     "provenance": [
      "chunk_lineage",
      "collection"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "many",
    "description": "Rankings to fuse."
   }
  ],
  "outputs": [
   {
    "name": "evidence",
    "type": {
     "kind": "ranked_evidence",
     "provenance": [
      "chunk_lineage",
      "collection"
     ],
     "score_kinds": [
      "rrf_v1"
     ],
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Fused ranking with rank provenance."
   }
  ],
  "capabilities": [],
  "effect": "pure",
  "bypass": null,
  "collection_param": null,
  "lever_params": {
   "rrf_k": "retrieval.hybrid_rrf_k"
  },
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "context.assemble",
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
  "version": 1,
  "title": "Assemble context",
  "family": "context",
  "description": "Expand lineage neighbours and merge overlapping chunks.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "expand_window": {
     "default": 0,
     "maximum": 10,
     "minimum": 0,
     "title": "Expand Window",
     "type": "integer"
    }
   },
   "title": "ContextParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "evidence",
    "type": {
     "kind": "ranked_evidence",
     "provenance": [
      "chunk_lineage",
      "collection"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Selected evidence."
   }
  ],
  "outputs": [
   {
    "name": "context",
    "type": {
     "kind": "context",
     "provenance": [
      "chunk_lineage",
      "collection"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Assembled context rows."
   }
  ],
  "capabilities": [
   "store"
  ],
  "effect": "read_only",
  "bypass": null,
  "collection_param": null,
  "lever_params": {},
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "prepare.enrich",
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
  "version": 1,
  "title": "Extract metadata",
  "family": "prepare",
  "description": "Extract file-level metadata for unstructured reads with the owning store.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "taxonomy_mode": {
     "anyOf": [
      {
       "enum": [
        "category",
        "file_type"
       ],
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Taxonomy Mode"
    }
   },
   "title": "EnrichParams",
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
    "description": "Documents to enrich."
   }
  ],
  "outputs": [
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
    "description": "Documents with file-level metadata."
   }
  ],
  "capabilities": [
   "store"
  ],
  "effect": "model_call",
  "bypass": {
   "input_port": "documents",
   "output_port": "documents"
  },
  "collection_param": null,
  "lever_params": {
   "taxonomy_mode": "metadata.taxonomy_mode"
  },
  "free_text_params": [],
  "index_shaping": true,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "retrieve.dense",
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
  "version": 1,
  "title": "Dense retrieval",
  "family": "retrieve",
  "description": "Embed the query and read the nearest chunks.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "collection": {
     "anyOf": [
      {
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Collection"
    }
   },
   "title": "CollectionParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "query",
    "type": {
     "kind": "query",
     "provenance": [],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Query text or a prepared query."
   }
  ],
  "outputs": [
   {
    "name": "evidence",
    "type": {
     "kind": "ranked_evidence",
     "provenance": [
      "chunk_lineage",
      "collection"
     ],
     "score_kinds": [
      "dense_similarity_v1"
     ],
     "embedding_identity": true,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Dense similarity ranking."
   }
  ],
  "capabilities": [
   "embedder",
   "store"
  ],
  "effect": "model_call",
  "bypass": null,
  "collection_param": "collection",
  "lever_params": {},
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "retrieve.prepare_query",
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
  "version": 1,
  "title": "Prepare query",
  "family": "retrieve",
  "description": "Resolve top-k, threshold, rerank policy and the candidate pool once.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "collection": {
     "anyOf": [
      {
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Collection"
    },
    "top_k": {
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
     "title": "Top K"
    },
    "similarity_threshold": {
     "anyOf": [
      {
       "maximum": 1.0,
       "minimum": 0.0,
       "type": "number"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Similarity Threshold"
    },
    "rerank": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Rerank"
    },
    "fetch_k": {
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
     "title": "Fetch K"
    },
    "metadata_filter": {
     "anyOf": [
      {
       "additionalProperties": true,
       "type": "object"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Metadata Filter"
    }
   },
   "title": "PrepareQueryParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "query",
    "type": {
     "kind": "query",
     "provenance": [],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Query text."
   }
  ],
  "outputs": [
   {
    "name": "query",
    "type": {
     "kind": "query",
     "provenance": [
      "collection"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Prepared query."
   }
  ],
  "capabilities": [
   "store"
  ],
  "effect": "read_only",
  "bypass": null,
  "collection_param": "collection",
  "lever_params": {
   "top_k": "retrieval.top_k",
   "similarity_threshold": "retrieval.similarity_threshold",
   "rerank": "retrieval.rerank_enabled"
  },
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 }
];
