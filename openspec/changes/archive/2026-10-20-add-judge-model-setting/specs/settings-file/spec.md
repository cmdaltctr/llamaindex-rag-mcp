## MODIFIED Requirements

### Requirement: Hand edits apply without a restart

`omrg web` SHALL notice a change to `omrg.jsonc` before it serves the next request that reads settings. Settings that apply at once SHALL use the new value from that request on: provider addresses, provider keys, the Chat provider and model, the claim check judge provider and model (`answer.verify_provider`, `answer.verify_model`), context windows, llama.cpp server values, `web_max_upload_mib` and `mcp_http_enabled`. The CLI and the stdio MCP server SHALL read the file at launch.

#### Scenario: Edit the Chat model by hand

- **WHEN** `omrg web` runs and the user changes `answer.model` in `omrg.jsonc`
- **THEN** the next answer MUST use the new model with no restart, and Settings MUST show it from `omrg.jsonc`

#### Scenario: Edit the judge model by hand

- **WHEN** `omrg web` runs and the user changes `answer.verify_model` in `omrg.jsonc`
- **THEN** the next answer with claim checks on MUST use the new judge model with no restart, and the Configuration section MUST NOT show "Restart to apply" for it

#### Scenario: Edit the upload limit by hand

- **WHEN** the user sets `web_max_upload_mib` to 200 in the file while the server runs
- **THEN** the next upload MUST be checked against 200 MiB

### Requirement: Some settings apply only after a restart

`web_port` and the engine settings (embedding, vector store, chunking, ingestion, retrieval, metadata, OCR, and the `answer` members other than `provider`, `model`, `verify_provider` and `verify_model`) SHALL apply at the next launch of the process. `omrg web` SHALL keep the values it started with and SHALL report each such key whose file value differs from it.

#### Scenario: Edit top-k by hand

- **WHEN** `omrg web` runs and the user changes `retrieval.top_k` in `omrg.jsonc`
- **THEN** searches MUST keep the launch value, and `GET /v1/settings/configuration` MUST list `retrieval.top_k` as "Restart to apply"

#### Scenario: Edit verify_claims by hand

- **WHEN** `omrg web` runs and the user changes `answer.verify_claims` in `omrg.jsonc`
- **THEN** `GET /v1/settings/configuration` MUST list `answer.verify_claims` as "Restart to apply"

#### Scenario: Embedding model changed by hand

- **WHEN** the user changes `embed_model` and restarts, and a collection holds vectors from the old model
- **THEN** a search of that collection MUST fail with the existing embedding-stamp message and MUST NOT mix vectors
