## MODIFIED Requirements

### Requirement: Ollama LLM-based categorisation with hybrid category lookup
When `METADATA_EXTRACTION_MODE` is `"ollama"`, the system SHALL make a single HTTP POST request to the local Ollama `/api/generate` endpoint to classify the document. The request SHALL use the model specified by `OLLAMA_CLASSIFY_MODEL` env var (default `"qwen3:0.6b"`). Before sending the prompt, the system SHALL query ChromaDB for all unique category values currently in use across all metadata scan pages and SHALL include them in the prompt as "existing categories" alongside the seed categories from keyword mode. The prompt SHALL instruct the model to prefer an existing category when applicable, but to propose a new concise category label (1-3 words, lowercase) when no existing category fits. The prompt SHALL instruct the model to return a JSON object with keys `category`, `keywords`, and `summary`. On failure (Ollama unreachable, model not pulled, or invalid JSON response), the system SHALL fall back to `{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING.

#### Scenario: Successful classification reuses existing category
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB contains existing categories `["ai", "biology", "philosophy"]`
- **AND** the document is about machine learning
- **THEN** the prompt SHALL include "ai" as an existing category option
- **THEN** Ollama SHALL return `{"category": "ai", ...}` (reusing the exact existing label)

#### Scenario: Category exists beyond first metadata page
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** a category value exists only after the first metadata scan page
- **THEN** the existing category lookup SHALL still discover that category
- **THEN** the classification prompt SHALL include that category as an existing option

#### Scenario: First run with no existing categories
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB has no existing category values (empty collection)
- **THEN** the prompt SHALL include the seed categories from keyword mode as the initial taxonomy
- **THEN** classification SHALL proceed normally against the seed categories
