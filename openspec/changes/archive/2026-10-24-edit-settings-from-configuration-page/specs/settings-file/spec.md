## ADDED Requirements

### Requirement: The page may write every scalar engine setting except identity, storage and keys

The keys the Settings page may write SHALL include every setting of the Settings model whose value is a boolean, a number, a text or a fixed choice, other than the read-only keys. The read-only keys SHALL be `embed_provider`, `embed_model`, `local_backend`, `cloud_backend`, `llamacpp_embed_url`, `llamacpp_embed_model`, `openrouter_embed_model`, every key under `embedding.`, `vector_store`, `lancedb_uri`, `chroma_persist_dir`, `chroma_mode`, `collection_name`, `ocr_workers_dir`, every secret field, every internal field, `ingestion.ingest_extensions` and `metadata.keyword_rules`. A write SHALL check the value against the rule of its setting before it writes: the type, the lower and upper bound, and the accepted choices. A refused value SHALL answer 400 with the plain-English rule and SHALL NOT change the file. `null` SHALL remove the key, so the default applies.

#### Scenario: Retrieval setting written

- **WHEN** the page writes `retrieval.top_k` 20
- **THEN** `omrs.jsonc` MUST hold `"retrieval": {"top_k": 20}` merged with the existing block, and every other byte of the file MUST stay as it was

#### Scenario: Value outside its bound

- **WHEN** the page writes `answer.max_rounds` 12 and the setting allows 1 to 8
- **THEN** the write MUST be refused with the range rule and the file MUST NOT change

#### Scenario: Value outside its choices

- **WHEN** the page writes `metadata.extraction_mode` `magic`
- **THEN** the write MUST be refused with the list of accepted modes and the file MUST NOT change

#### Scenario: Identity key refused

- **WHEN** a request asks the server to write `embed_model`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Storage key refused

- **WHEN** a request asks the server to write `lancedb_uri`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Optional setting cleared

- **WHEN** the page writes `metadata.ollama_classify_timeout_override` `null`
- **THEN** the key MUST be removed from `omrs.jsonc` and the setting MUST use its default from the next read

### Requirement: The configuration save writes several keys under one revision

`PUT /v1/settings/configuration` SHALL take the browser session with the `manage` scope; a bearer credential SHALL NOT pass. It SHALL take a `revision` and a `changes` object of key and value. It SHALL check every change before it writes, and SHALL write all of them or none. It SHALL answer 409 with "omrs.jsonc changed on disk. Reload to see the new values." when the revision differs from the file, and SHALL answer 409 naming the variable when a key is set in the environment or `.env`. After a write, it SHALL return the same body as `GET /v1/settings/configuration`.

#### Scenario: Two keys saved together

- **WHEN** the page sends `retrieval.top_k` 20 and `retrieval.rerank_enabled` true with the current revision
- **THEN** both keys MUST be in the file and the response MUST show both with the source `config-file`

#### Scenario: One bad value stops the whole save

- **WHEN** the page sends `retrieval.top_k` 20 and `answer.max_rounds` 12
- **THEN** the server MUST answer 400 naming `answer.max_rounds` and MUST NOT write `retrieval.top_k`

#### Scenario: Locked by the environment

- **WHEN** `.env` sets `RETRIEVAL__TOP_K` and the page sends `retrieval.top_k` 20
- **THEN** the server MUST answer 409 naming `RETRIEVAL__TOP_K` and MUST NOT change the file

#### Scenario: Bearer token refused

- **WHEN** an MCP bearer token calls `PUT /v1/settings/configuration`
- **THEN** the server MUST answer 403 and MUST NOT change the file
