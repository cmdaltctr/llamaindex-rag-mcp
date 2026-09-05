## MODIFIED Requirements

### Requirement: Markdown files use heading-aware chunking with a size cap

When a model-matched embedding tokenizer is configured, the system SHALL chunk Markdown text using the Rust-backed `semantic-text-splitter` Markdown splitter with the tokenizer as its size calculator. The splitter SHALL prefer the largest meaningful Markdown structures that fit the configured `CHUNKING__MARKDOWN_CHUNK_SIZE` budget, including headings/sections, paragraphs, tables, lists, and sentences, before recursively splitting at smaller boundaries.

Text counts as Markdown when the source file has extension `.md`, **or** when the reader that produced it declares its emitted text format as `markdown`. The token budget SHALL be measured in the configured embedding tokenizer's units rather than a generic tokenizer or character approximation.

When no model-matched tokenizer is configured or the tokenizer cannot be resolved, the system SHALL preserve the existing MarkdownNodeParser/SentenceSplitter behaviour and SHALL NOT claim model-token-aware sizing.

Text from readers declaring `plain` SHALL retain the existing non-Markdown splitter behaviour and global `CHUNKING__CHUNK_SIZE` default.

#### Scenario: Markdown headings remain intact when sections fit

- **GIVEN** a Markdown document with multiple heading-bounded sections, each within `CHUNKING__MARKDOWN_CHUNK_SIZE` under the configured embedding tokenizer
- **WHEN** the document is ingested through the model-token-aware Markdown path
- **THEN** the splitter SHALL prefer section/structural boundaries rather than cutting solely at an arbitrary token position
- **AND** no produced chunk SHALL exceed the configured tokenizer budget

#### Scenario: Long heading-bounded section is further split

- **GIVEN** a Markdown section whose content exceeds `CHUNKING__MARKDOWN_CHUNK_SIZE` under the configured embedding tokenizer
- **WHEN** the document is ingested
- **THEN** that section SHALL be split into more than one chunk at progressively smaller meaningful boundaries
- **AND** every produced chunk SHALL remain within the configured tokenizer budget

#### Scenario: Non-Markdown files are unchanged

- **GIVEN** a `.txt` file, or a `.pdf` read by a reader declaring `plain`
- **WHEN** the file is ingested
- **THEN** chunking SHALL use the existing non-Markdown behaviour
- **AND** no heading metadata SHALL be fabricated

#### Scenario: Markdown-format reader output uses the structure-aware path

- **GIVEN** a `.pdf` read by a reader declaring its emitted text format as `markdown`
- **AND** a model-matched tokenizer is configured
- **WHEN** the file is ingested
- **THEN** the Rust-backed Markdown splitter SHALL process the emitted Markdown
- **AND** `CHUNKING__MARKDOWN_CHUNK_SIZE` SHALL be enforced in that tokenizer's units

#### Scenario: Markdown without headings still chunks

- **GIVEN** Markdown text with no headings but with paragraphs, lists, or other supported Markdown structure
- **WHEN** the file is ingested through the model-token-aware path
- **THEN** the splitter SHALL still produce non-empty chunks
- **AND** SHALL use the best available structural boundaries within the configured token cap

#### Scenario: Missing tokenizer preserves the existing path

- **GIVEN** Markdown input and no usable embedding tokenizer identity
- **WHEN** the file is ingested
- **THEN** the current MarkdownNodeParser/SentenceSplitter path SHALL be used
- **AND** the system SHALL NOT describe its size accounting as the embedding model's exact token count

#### Scenario: Markdown-format reader output uses the heading-aware path

- **GIVEN** a `.pdf` read by a reader declaring its emitted text format as `markdown`
- **AND** the legacy Markdown fallback path is active because no model-matched tokenizer is configured or it cannot be resolved
- **WHEN** the file is ingested
- **THEN** the heading-aware node parser SHALL run before sentence splitting
- **THEN** the emitted chunks SHALL carry `header_path`
- **THEN** the `CHUNKING__MARKDOWN_CHUNK_SIZE` budget SHALL apply

#### Scenario: Reader-produced Markdown honours the recovery knobs

- **GIVEN** reader-produced Markdown text
- **WHEN** the file is ingested
- **THEN** `ensure_heading_metadata`, `apply_heading_prepend` and
  `drop_small_markdown_chunks` SHALL apply with the same configured behaviour
  they have for `.md` files

### Requirement: Markdown files support configurable Markdown-only recovery knobs

The Markdown branch SHALL support a Markdown-only chunk-size override, optional heading-path prepend, optional small-chunk filtering, and defensive heading metadata propagation. Heading prepend and small-chunk filtering SHALL remain opt-in. Defensive heading metadata propagation SHALL be idempotent.

When the model-token-aware Markdown path is active, small-chunk filtering SHALL use the configured embedding tokenizer's actual token count. It SHALL NOT use the four-characters-per-token approximation. The approximation MAY remain only on the legacy fallback path until that path is retired separately.

#### Scenario: Markdown branch can use a different chunk size from non-Markdown files

- **GIVEN** `CHUNKING__CHUNK_SIZE=512` and `CHUNKING__MARKDOWN_CHUNK_SIZE=1024`
- **WHEN** Markdown and non-Markdown documents are ingested
- **THEN** the Markdown branch SHALL use the 1024-unit Markdown budget under its active tokenizer/splitter
- **AND** non-Markdown files SHALL continue using the 512-unit non-Markdown setting

#### Scenario: Heading metadata is defensively preserved

- **GIVEN** a Markdown structure is split into more than one child chunk
- **WHEN** the children are emitted
- **THEN** the system SHALL copy available heading-path metadata from the source node when a child omitted it
- **AND** repeated application SHALL NOT duplicate or corrupt existing heading metadata

#### Scenario: Heading text can be prepended before embedding

- **GIVEN** the heading-prepend recovery option is enabled
- **AND** a Markdown chunk has a non-empty heading path
- **WHEN** the chunk text is finalised for embedding
- **THEN** the heading path SHALL be prepended once
- **AND** repeated processing SHALL NOT prepend the same prefix twice

#### Scenario: Small Markdown chunks can be filtered with exact model tokens

- **GIVEN** the small-chunk fraction is greater than zero
- **AND** the model-token-aware Markdown path is active
- **WHEN** Markdown chunks are emitted
- **THEN** each chunk's size SHALL be measured with the configured embedding tokenizer
- **AND** chunks below `CHUNKING__MARKDOWN_CHUNK_SIZE * CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION` tokenizer units SHALL be filtered according to the configured recovery behaviour
- **AND** the system SHALL log how many chunks were filtered

#### Scenario: Small Markdown chunks can be filtered

- **GIVEN** `CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION > 0.0`
- **AND** the legacy Markdown fallback path is active because no model-matched tokenizer is configured or it cannot be resolved
- **WHEN** Markdown chunks are emitted after splitting
- **THEN** chunks smaller than `CHUNKING__MARKDOWN_CHUNK_SIZE * 4 * CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION` characters SHALL be filtered before embedding
- **AND** the system SHALL log how many chunks were filtered

## ADDED Requirements

### Requirement: Embedding tokenizer identity SHALL be explicit and independent from inference transport

The system SHALL support an injected embedding-tokenizer identity for exact Markdown token accounting. The identity SHALL refer to the tokenizer/model artefact used for counting tokens, independently from whether embedding inference is served by Ollama, llama.cpp, OpenRouter, or another provider.

The system SHALL NOT infer a Hugging Face repository by substring-matching an inference-server alias.

#### Scenario: Qwen inference through Ollama uses the Qwen Hugging Face tokenizer

- **GIVEN** embedding inference is served through Ollama using Qwen3-Embedding-4B
- **AND** `EMBEDDING__TOKENIZER_MODEL=Qwen/Qwen3-Embedding-4B`
- **WHEN** structured Markdown is chunked
- **THEN** token budgeting SHALL use the tokenizer resolved from `Qwen/Qwen3-Embedding-4B`
- **AND** the chunker SHALL NOT call the Ollama inference server merely to count tokens

#### Scenario: Tokenizer is cached by identity

- **GIVEN** multiple files are chunked with the same embedding-tokenizer identity
- **WHEN** the tokenizer is requested repeatedly
- **THEN** the system SHALL reuse the resolved tokenizer rather than reloading it for every chunk or file

#### Scenario: Tokenizer resolution is pinned and works from cache

- **GIVEN** an embedding-tokenizer identity and revision are configured
- **AND** the tokenizer artefact is present in the local cache
- **WHEN** Markdown is chunked with no network access available
- **THEN** the tokenizer SHALL resolve from the cache at the configured revision
- **AND** chunking SHALL NOT depend on reaching a remote model hub at ingest time

#### Scenario: Tokenizer truncation is disabled before counting

- **GIVEN** a resolved embedding tokenizer whose loaded configuration enables truncation
- **WHEN** it is used as the splitter's size calculator
- **THEN** truncation SHALL be disabled on it first
- **AND** a text longer than the tokenizer's truncation limit SHALL report its full token count rather than the capped limit

### Requirement: The model-token-aware Markdown path SHALL define one complete size and heading contract

The replacement splitter SHALL derive heading ancestry from the source Markdown itself. It SHALL locate each emitted chunk in the source text using the splitter's chunk-offset API, resolve the heading chain enclosing that offset, and write the result to `header_path` before the recovery hooks run.

Heading derivation SHALL NOT depend on `ensure_heading_metadata`. That helper copies heading metadata that a parent node already carries; the Rust splitter emits text without a parent node, so on this path there is nothing for it to copy. The helper SHALL remain in the pipeline as the idempotent guard it already is.

The configured `CHUNKING__CHUNK_OVERLAP` SHALL be passed to the splitter as its own overlap, measured in the same tokenizer units as the capacity. Because the splitter requires the overlap to be strictly less than the capacity, the system SHALL reject a configuration whose overlap is greater than or equal to `CHUNKING__MARKDOWN_CHUNK_SIZE` at the composition boundary, naming both settings.

The token cap SHALL govern the chunk text as finalised for embedding, which includes any prepended heading path. When heading prepend is enabled, the splitter SHALL be given a capacity reduced by the token length of the prefix that will be prepended, so a prepended chunk cannot exceed the configured budget.

The cap SHALL NOT be defined over the complete LlamaIndex embedding payload. Retained metadata keys are added to that payload after chunking and are not known when the splitter runs. Their worst-case token overhead SHALL be measured and reported as experiment evidence instead of budgeted.

#### Scenario: Heading path is derived on the model-token-aware path

- **GIVEN** Markdown with nested headings and a model-matched tokenizer configured
- **WHEN** the Rust-backed Markdown splitter emits chunks
- **THEN** each chunk SHALL carry the `header_path` of the heading chain enclosing its position in the source Markdown
- **AND** the path SHALL be derived from the source text rather than copied from a parent node

#### Scenario: Configured overlap is applied in tokenizer units

- **GIVEN** `CHUNKING__CHUNK_OVERLAP` is non-zero and below the Markdown chunk size
- **WHEN** an oversized Markdown section is split
- **THEN** adjacent chunks SHALL share overlapping text
- **AND** the overlap SHALL be measured in the configured embedding tokenizer's units

#### Scenario: Overlap at or above the chunk size is rejected

- **GIVEN** `CHUNKING__CHUNK_OVERLAP` is greater than or equal to `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **WHEN** the model-token-aware Markdown path is constructed
- **THEN** the system SHALL fail at the composition boundary naming both settings
- **AND** it SHALL NOT surface the splitter's own error part-way through an ingestion batch

#### Scenario: Heading prepend stays within the token cap

- **GIVEN** heading prepend is enabled
- **AND** a Markdown section whose content alone would fill `CHUNKING__MARKDOWN_CHUNK_SIZE` exactly under the configured tokenizer
- **WHEN** the section is chunked and its heading path is prepended
- **THEN** the finalised chunk text SHALL still be within `CHUNKING__MARKDOWN_CHUNK_SIZE` tokenizer units
- **AND** the reserved prefix budget SHALL come from the splitter capacity rather than from a post-hoc truncation

#### Scenario: Metadata overhead is measured, not budgeted

- **WHEN** the chunking experiment runs
- **THEN** it SHALL record the worst-case token count of the complete embedding payload against the chunk-text token count
- **AND** the cap enforced during chunking SHALL remain the chunk-text cap
