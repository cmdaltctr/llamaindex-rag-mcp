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
