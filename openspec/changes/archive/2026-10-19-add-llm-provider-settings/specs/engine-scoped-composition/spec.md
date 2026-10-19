# Spec Delta

## ADDED Requirements

### Requirement: A running Engine can take new LLM provider values

The Engine SHALL let its owner hand it new server-default settings that differ only in LLM provider addresses, keys and the answer provider and model. The Engine SHALL refuse any other difference. After the change, the next answer, judge, ingest and graph run SHALL use the new values through the factories the composition root gave. A call that already started SHALL finish with the old values.

#### Scenario: Next answer uses the new model

- **WHEN** the owner hands the Engine a new answer model name after one answer
- **THEN** the next answer MUST use a model built with the new name, and the old model MUST NOT be used again

#### Scenario: Next ingest uses the new key

- **WHEN** metadata extraction uses OpenRouter and the owner hands the Engine a new OpenRouter key
- **THEN** the next ingest MUST resolve settings that hold the new key

#### Scenario: Call in progress keeps its values

- **WHEN** the owner hands the Engine new values while an answer waits for its model reply
- **THEN** that answer MUST complete with the model it started with

#### Scenario: Embedding settings refused

- **WHEN** the owner hands the Engine settings whose embedding provider, embedding model or embedding address differs
- **THEN** the Engine MUST raise an error and MUST keep its current settings

#### Scenario: Other resources unchanged

- **WHEN** the owner hands the Engine new provider values
- **THEN** the Engine's embedder, store and reranker MUST stay the same objects
