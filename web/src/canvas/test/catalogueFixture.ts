/* Subset of the real operation catalogue (`build_operation_catalogue().describe(...)`), captured 2026-10-13. */
import type { OperationDescriptor } from "../../api/pipelines";

export const CATALOGUE: OperationDescriptor[] = [
 {
  "operation_id": "combine.rrf",
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
 },
 {
  "operation_id": "retrieve.sparse",
  "version": 1,
  "title": "Sparse retrieval",
  "family": "retrieve",
  "description": "Rank chunks by keywords with the configured sparse backend.",
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
      "sparse_rank_v1"
     ],
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Rank-only sparse ranking."
   }
  ],
  "capabilities": [
   "store"
  ],
  "effect": "read_only",
  "bypass": null,
  "collection_param": "collection",
  "lever_params": {},
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "select.rerank",
  "version": 1,
  "title": "Cross-encoder rerank",
  "family": "select",
  "description": "Re-score evidence; a failure keeps the pre-rerank scores.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "enabled": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Enabled"
    }
   },
   "title": "RerankParams",
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
     "score_kinds": [
      "dense_similarity_v1",
      "reranker_sigmoid_v1",
      "rrf_v1"
     ],
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Scored ranked evidence."
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
      "dense_similarity_v1",
      "reranker_sigmoid_v1",
      "rrf_v1"
     ],
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Reranked or unchanged evidence."
   }
  ],
  "capabilities": [
   "reranker"
  ],
  "effect": "model_call",
  "bypass": {
   "input_port": "evidence",
   "output_port": "evidence"
  },
  "collection_param": null,
  "lever_params": {
   "enabled": "retrieval.rerank_enabled"
  },
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "select.threshold",
  "version": 1,
  "title": "Threshold and top-k",
  "family": "select",
  "description": "Apply the score-kind-aware threshold, then keep top-k.",
  "parameters": {
   "additionalProperties": false,
   "properties": {},
   "title": "NoParams",
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
     "score_kinds": [
      "dense_similarity_v1",
      "reranker_sigmoid_v1",
      "rrf_v1"
     ],
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Scored ranked evidence."
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
      "dense_similarity_v1",
      "reranker_sigmoid_v1",
      "rrf_v1"
     ],
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Selected evidence."
   }
  ],
  "capabilities": [],
  "effect": "pure",
  "bypass": null,
  "collection_param": null,
  "lever_params": {},
  "free_text_params": [],
  "index_shaping": false,
  "available": true,
  "unavailable_reasons": []
 },
 {
  "operation_id": "verify.claims",
  "version": 1,
  "title": "Verify claims",
  "family": "verify",
  "description": "Opt-in claim check with the judge model. A missing or failing judge reports verification_skipped with its reason.",
  "parameters": {
   "additionalProperties": false,
   "properties": {
    "verify_claims": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Verify Claims"
    }
   },
   "title": "VerifyClaimsParams",
   "type": "object"
  },
  "inputs": [
   {
    "name": "answer",
    "type": {
     "kind": "answer",
     "provenance": [
      "chunk_lineage"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Answer result with resolved citations."
   }
  ],
  "outputs": [
   {
    "name": "answer",
    "type": {
     "kind": "answer",
     "provenance": [
      "chunk_lineage"
     ],
     "score_kinds": null,
     "embedding_identity": false,
     "reader_declarations": []
    },
    "cardinality": "one",
    "description": "Answer result with verification labels."
   }
  ],
  "capabilities": [],
  "effect": "model_call",
  "bypass": {
   "input_port": "answer",
   "output_port": "answer"
  },
  "collection_param": null,
  "lever_params": {
   "verify_claims": "answer.verify_claims"
  },
  "free_text_params": [],
  "index_shaping": false,
  "available": false,
  "unavailable_reasons": [
   "Capability 'judge_model' is not available: no judge model is configured."
  ]
 }
];
