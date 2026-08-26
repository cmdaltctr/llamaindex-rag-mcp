## ADDED Requirements

### Requirement: Code files use a verifiably active AST-aware splitter

For content classified as supported source code, the system SHALL invoke LlamaIndex `CodeSplitter` using parameter names and units supported by the locked LlamaIndex version. Code splitting configuration SHALL use code-specific units rather than reusing document token settings under incompatible names.

The chunking configuration SHALL expose explicit code-oriented settings for line count, line overlap and maximum character ceiling (or the exact successor fields required by a future supported LlamaIndex API). Document `chunk_size` / `chunk_overlap` remain token-oriented settings for SentenceSplitter and SHALL NOT be passed to CodeSplitter as though they had the same semantics.

#### Scenario: Supported Python code uses AST path
- **GIVEN** a valid Python source fixture whose AST-aware boundaries differ from SentenceSplitter output
- **WHEN** type-aware ingestion chunks the file
- **THEN** the effective strategy MUST be `code`
- **AND** the emitted boundaries MUST satisfy the CodeSplitter structural fixture assertions
- **AND** no fallback SHALL have occurred

#### Scenario: Constructor/API regression
- **GIVEN** the installed LlamaIndex CodeSplitter API no longer accepts the arguments the project supplies
- **WHEN** the code chunker contract test runs
- **THEN** the test MUST fail
- **AND** a successful SentenceSplitter fallback MUST NOT make the CodeSplitter success test pass

### Requirement: Code chunking fallback is observable

When AST-aware code splitting fails and the production policy falls back to SentenceSplitter, the system SHALL surface the requested strategy, effective strategy and fallback reason in internal diagnostics/logging. Experiments that manipulate chunking strategy SHALL treat such fallback as an invalid cell rather than silently measuring the fallback implementation.

#### Scenario: Parser failure falls back in production
- **GIVEN** CodeSplitter raises for a supported source file
- **WHEN** normal ingestion runs
- **THEN** SentenceSplitter MAY be used according to the existing graceful-degradation policy
- **AND** diagnostics MUST identify `requested=code`, `effective=sentence`, and the failure reason

#### Scenario: Chunker experiment observes fallback
- **GIVEN** an experiment declares CodeSplitter as the treatment
- **WHEN** fallback occurs
- **THEN** experiment preflight or the measured cell MUST abort as invalid

### Requirement: Markdown/sentence helper paths honour the same configured post-processing

Any public/internal helper that implements the same Markdown chunking strategy SHALL forward the configured heading-prepend and minimum-chunk-fraction values consistently. Calling the standalone sentence/Markdown helper SHALL NOT silently revert those knobs to function defaults while the main ingestion path honours them.

#### Scenario: Same Markdown settings through two entry points
- **GIVEN** heading prepend and a non-zero minimum chunk fraction are configured
- **WHEN** the same fixture is chunked through the main ingestion path and the standalone sentence/Markdown strategy helper
- **THEN** both paths SHALL apply equivalent configured post-processing
