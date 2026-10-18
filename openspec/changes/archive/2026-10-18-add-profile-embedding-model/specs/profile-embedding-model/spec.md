# Spec Delta

## Purpose

Let a user profile choose the embedding model that its collections use, and keep each collection's vectors from one model only. The model locks when a bound collection holds vectors.

## ADDED Requirements

### Requirement: A user profile names its embedding model

A user profile SHALL store an embedding choice: one provider from the embedding provider registry and one model name. An empty choice SHALL mean the server default, which the `EMBED_*` settings define. The choice SHALL belong to the profile, not to a graph node. Graph node parameters and graph overrides SHALL NOT set the embedding provider or model.

#### Scenario: A profile stores a chosen model

- **GIVEN** a user profile with no embedding choice
- **WHEN** the user saves provider `ollama` and model `nomic-embed-text` for that profile
- **THEN** the profile SHALL return provider `ollama` and model `nomic-embed-text`

#### Scenario: An empty choice uses the server default

- **GIVEN** a user profile with no embedding choice
- **AND** the server default is provider `llamacpp` and model `Qwen3-Embedding-0.6B-Q8_0.gguf`
- **WHEN** a client reads the profile
- **THEN** the profile SHALL report the server default as its effective model
- **AND** the profile SHALL mark the model as the server default

#### Scenario: A graph cannot set the model

- **GIVEN** a graph with a node parameter or a graph override for `embed_model`
- **WHEN** the graph is validated
- **THEN** validation SHALL report that the host owns the setting
- **AND** the run SHALL NOT start

#### Scenario: Duplicating a profile copies its choice

- **GIVEN** a user profile with an embedding choice
- **WHEN** the user duplicates the profile
- **THEN** the new profile SHALL have the same embedding choice

### Requirement: Built-in profiles use the server default model

The built-in profiles `documents` and `codebase` SHALL always use the server default embedding model. A request to change the embedding choice of a built-in profile SHALL be refused.

#### Scenario: A built-in profile refuses a model change

- **WHEN** a client requests a model change for the `documents` profile
- **THEN** the API SHALL refuse the request
- **AND** the message SHALL tell the user to duplicate the profile first

### Requirement: Collection operations use the profile's model

Each ingest, search, answer and graph run on a collection SHALL embed with the effective model of that collection's profile. A collection without a profile tag SHALL use the server profile and the server default model. No operation on a collection SHALL embed with another model.

#### Scenario: Ingest uses the profile model

- **GIVEN** collection `papers` is bound to a user profile with model B
- **AND** the server default is model A
- **WHEN** a file is ingested into `papers`
- **THEN** every chunk vector SHALL come from model B
- **AND** no vector SHALL come from model A

#### Scenario: A graph run uses the collection's model

- **GIVEN** collection `papers` is bound to a user profile with model B
- **WHEN** a graph runs for `papers`
- **THEN** the embed and dense retrieval steps SHALL use model B

### Requirement: Queries are embedded with the collection's model

Search and answer SHALL embed the query with the effective model of the collection's profile. The store SHALL compare the collection's stamp with that model before it runs a dense or a native sparse query. When the stamp names another model, the query SHALL fail with the existing mismatch message. The system SHALL NOT fall back to the server model.

#### Scenario: Search embeds the query with the collection's model

- **GIVEN** collection `papers` is bound to a user profile with model B
- **AND** the server default is model A
- **WHEN** a client searches `papers`
- **THEN** model B SHALL embed the query
- **AND** model A SHALL NOT embed the query

#### Scenario: A stale stamp fails closed

- **GIVEN** collection `papers` is stamped with model A
- **AND** the effective model of its profile is model B
- **WHEN** a client searches `papers`
- **THEN** the search SHALL fail before the store runs the query
- **AND** the message SHALL name model A and model B

#### Scenario: Sparse search on a profile collection is not refused

- **GIVEN** collection `papers` is stamped with model B
- **AND** its profile uses model B
- **AND** the server default is model A
- **WHEN** a native sparse query runs on `papers`
- **THEN** the identity guard SHALL accept the query

### Requirement: Graph preflight checks the collection's model

Graph preflight SHALL compare each bound collection's stamp with the effective model of the profile that the run uses for that collection. A difference SHALL be a blocking preflight issue that names both models.

#### Scenario: Preflight accepts a matching profile model

- **GIVEN** collection `papers` is stamped with model B
- **AND** the graph runs for `papers` with a profile that uses model B
- **AND** the server default is model A
- **WHEN** the graph is validated
- **THEN** preflight SHALL NOT report an embedding identity mismatch

#### Scenario: Preflight refuses a different model

- **GIVEN** collection `papers` is stamped with model A
- **AND** the graph runs for `papers` with a profile that uses model B
- **WHEN** the graph is validated
- **THEN** preflight SHALL report an embedding identity mismatch that names model A and model B

### Requirement: The model locks when a bound collection holds vectors

A model change SHALL be allowed only when each collection bound to the profile is in one of two states. The collection has no stamp and no rows. Or its stamp names the requested effective model. A collection holds vectors when it has a stamp or at least one row. A stamped collection with no rows SHALL stay locked, because the store keeps its vector size.

#### Scenario: A profile with only empty collections may change

- **GIVEN** a user profile bound to collection `drafts`
- **AND** `drafts` has no stamp and no rows
- **WHEN** the user changes the model
- **THEN** the change SHALL be saved

#### Scenario: A stamped collection locks the model

- **GIVEN** a user profile bound to collection `papers`
- **AND** `papers` holds vectors stamped with model A
- **WHEN** the user requests model B
- **THEN** the API SHALL refuse the change
- **AND** the profile SHALL keep model A

#### Scenario: An emptied but stamped collection stays locked

- **GIVEN** collection `papers` is stamped with model A
- **AND** all rows of `papers` were deleted
- **WHEN** the user requests model B for the bound profile
- **THEN** the API SHALL refuse the change

#### Scenario: Rows without a stamp lock the model

- **GIVEN** collection `legacy` has rows but no stamp
- **WHEN** the user requests a model change for the bound profile
- **THEN** the API SHALL refuse the change
- **AND** the refusal SHALL say that the model that made the vectors is not recorded

#### Scenario: A change back to the stamped model is allowed

- **GIVEN** collection `papers` is stamped with model A
- **AND** the bound profile uses model B
- **WHEN** the user requests model A
- **THEN** the change SHALL be saved

#### Scenario: A profile with no bound collections may change

- **GIVEN** a user profile that no collection uses
- **WHEN** the user changes the model
- **THEN** the change SHALL be saved

### Requirement: A refused model change names the collections

A refused model change SHALL return a conflict response. The response SHALL list each collection that blocks the change, with its stamped provider and model (or "not recorded") and its chunk count.

#### Scenario: The refusal lists the blocking collections

- **GIVEN** collections `papers` (model A, 120 chunks) and `notes` (model A, 0 chunks, stamped) use one profile
- **WHEN** the user requests model B
- **THEN** the response SHALL be a conflict
- **AND** it SHALL list `papers` with model A and 120 chunks
- **AND** it SHALL list `notes` with model A and 0 chunks

### Requirement: Binding refuses a different model

Binding a profile to a collection SHALL be refused when the collection holds vectors and its stamp does not name the profile's effective model. This SHALL apply to built-in and user profiles, and to the preview and the confirm step. Binding to a collection with rows but no stamp SHALL be refused unless the profile's effective model is the server default.

#### Scenario: Binding to a collection made with another model

- **GIVEN** collection `papers` is stamped with model A
- **AND** a user profile uses model B
- **WHEN** a client asks to bind the profile to `papers`
- **THEN** the API SHALL refuse the request with a conflict
- **AND** the message SHALL name model A and model B
- **AND** the collection's profile tag SHALL NOT change

#### Scenario: Binding to a collection made with the same model

- **GIVEN** collection `papers` is stamped with model B
- **AND** a user profile uses model B
- **WHEN** a client asks to bind the profile to `papers`
- **THEN** the API SHALL allow the binding

#### Scenario: Binding to an empty unstamped collection

- **GIVEN** collection `drafts` has no stamp and no rows
- **WHEN** a client binds a profile with any model to `drafts`
- **THEN** the API SHALL allow the binding
- **AND** the first ingest SHALL stamp the profile's model

### Requirement: Check model probes the model

The system SHALL provide a model check for a provider and a model name. The check SHALL embed one short probe text and return the vector size. For llama.cpp, which ignores the requested name, it SHALL first confirm that the server lists the model. It SHALL fail when the provider is not installed, the model is not listed, the call fails, or the vector length is outside the norm tolerance, with a plain reason. Saving a new model SHALL run the same check.

#### Scenario: A good model passes the check

- **GIVEN** the provider can embed with the model
- **AND** the probe returns a unit-length vector with 1024 values
- **WHEN** the user checks the model
- **THEN** the check SHALL pass
- **AND** it SHALL report a vector size of 1024

#### Scenario: A model that the llama.cpp server does not list fails

- **GIVEN** the llama.cpp server lists only model A
- **WHEN** the user checks model B on that server
- **THEN** the check SHALL fail before the probe embedding
- **AND** the reason SHALL say that the server does not serve model B
- **AND** the reason SHALL list the model names that the server serves

#### Scenario: A model that the provider cannot load fails

- **GIVEN** Ollama has not pulled model B
- **WHEN** the user checks model B
- **THEN** the check SHALL fail
- **AND** the reason SHALL include the provider's error text with credentials removed

#### Scenario: A model with non-unit vectors fails

- **GIVEN** the probe vector length is 1.4
- **AND** the norm guard is enabled
- **WHEN** the user checks the model
- **THEN** the check SHALL fail
- **AND** the reason SHALL say that ingestion would refuse these vectors

#### Scenario: A missing optional dependency fails clearly

- **GIVEN** the `openrouter` extra is not installed
- **WHEN** the user checks an OpenRouter model
- **THEN** the check SHALL fail
- **AND** the reason SHALL name the extra to install

#### Scenario: Saving runs the check

- **GIVEN** the provider cannot embed with the requested model
- **WHEN** the user saves the model for an unlocked profile
- **THEN** the save SHALL be refused with the check reason
- **AND** the profile SHALL keep its previous model

#### Scenario: Credentials never appear in a check reason

- **GIVEN** the provider error text contains the configured API key
- **WHEN** the check fails
- **THEN** the reason SHALL NOT contain the key

### Requirement: A new vector size applies only to collections without vectors

A model with a different vector size SHALL reach only collections that have no stamp and no rows. The first write SHALL fix the collection's vector size and stamp. The profile SHALL record the vector size from its last passing check.

#### Scenario: A new model with another size fills a new collection

- **GIVEN** a user profile changed from a 1024-value model to a 768-value model
- **AND** collection `fresh` is bound to it and has no stamp and no rows
- **WHEN** a file is ingested into `fresh`
- **THEN** `fresh` SHALL hold 768-value vectors
- **AND** its stamp SHALL name the new model

#### Scenario: The profile shows the recorded size

- **WHEN** a model check passes for a profile's new model
- **AND** the model is saved
- **THEN** the profile SHALL return the vector size from that check

### Requirement: The Engine owns one embedder per model

An Engine SHALL hold at most one embedder for each (provider, model) pair. The server default embedder SHALL be one of them. The Engine SHALL build the other embedders on first use, SHALL release all of them when it closes, and SHALL NOT share them with another Engine.

#### Scenario: One embedder serves each model

- **GIVEN** two collections bound to profiles with the same model B
- **WHEN** both collections are searched in one Engine
- **THEN** one embedder instance SHALL serve both searches

#### Scenario: Two Engines keep separate embedders

- **GIVEN** two Engines in one process that both use model B for a collection
- **WHEN** each Engine searches its collection
- **THEN** each Engine SHALL use its own embedder instance

#### Scenario: Closing an Engine releases its embedders

- **WHEN** an Engine closes
- **THEN** it SHALL release every embedder it built
- **AND** the embedders of another Engine SHALL stay available

### Requirement: The Embed step shows the model and the lock

The Studio Embed step SHALL show the effective embedding model of the open profile. For an unlocked user profile it SHALL offer a provider list, a model name field, a "Check model" button and the result. For a locked user profile it SHALL show the lock text instead of the controls. For a built-in profile it SHALL show the server default as read-only text.

#### Scenario: An unlocked profile shows the controls

- **GIVEN** a user profile with no collections that hold vectors
- **WHEN** the user opens the Embed step
- **THEN** the step SHALL show the provider list, the model field and "Check model"

#### Scenario: A locked profile says why

- **GIVEN** a user profile bound to collection `papers`
- **AND** `papers` holds vectors made with `nomic-embed-text`
- **WHEN** the user opens the Embed step
- **THEN** the step SHALL show "Locked: papers already holds vectors made with nomic-embed-text. Create a new collection to use another model."
- **AND** the step SHALL NOT show the model controls

#### Scenario: A built-in profile shows the server default

- **WHEN** the user opens the Embed step of the `documents` profile
- **THEN** the step SHALL show the server default model as read-only text
