/* Part 2 of 2: retrieve (sparse), select, verify. */
import type { OperationDescriptor } from "../../api/pipelines";

export const CATALOGUE_PART_TWO: OperationDescriptor[] = [
 {
  "operation_id": "retrieve.sparse",
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
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
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
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
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
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
  "option_params": {},
  "unavailable_options": {},
  "inherited_values": {},
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
