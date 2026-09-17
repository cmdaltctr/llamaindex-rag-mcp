# codebase-rag-evaluation Specification

## ADDED Requirements

### Requirement: Codebase baseline uses a frozen RepoProbe subset

Experiment 34B SHALL evaluate the current OMRG `codebase` profile on a small frozen RepoProbe subset.

#### Scenario: Repository identity is not pinned
- **WHEN** a repository does not have a frozen commit SHA or equivalent immutable identity
- **THEN** it SHALL NOT be included in the measured 34B baseline

### Requirement: Codebase baseline uses the shipped codebase profile

The measured run SHALL preserve the current codebase retrieval policy, including hybrid retrieval and the profile's reranker setting.

#### Scenario: Document reranking is enabled only for the benchmark
- **WHEN** reranking is enabled contrary to the frozen codebase profile
- **THEN** the run SHALL be labelled exploratory
- **AND** it SHALL NOT replace the 34B baseline

### Requirement: Codebase retrieval and answer quality are reported separately

The benchmark SHALL preserve retrieval-stage evidence separately from final answer scoring.

#### Scenario: The final answer is wrong despite retrieving the correct source
- **WHEN** the gold repository evidence is present in the retrieved set
- **BUT** the generated answer is incorrect
- **THEN** the report SHALL attribute retrieval as successful
- **AND** it SHALL record the answer-stage failure separately

### Requirement: RepoProbe subset identity is frozen

The measured subset SHALL freeze repository names, repository commit SHAs, question IDs, query order, and scorer version before execution.

#### Scenario: A repository advances after freeze
- **WHEN** the remote repository HEAD changes
- **THEN** the measured run SHALL still use the frozen commit
- **AND** a run on the new commit SHALL use a new benchmark revision

### Requirement: Codebase baseline remains small and sequential

The first 34B baseline SHALL use only the approved small subset and SHALL run separately from 34A.

#### Scenario: Both profiles are scheduled concurrently on the Mac
- **WHEN** 34A is still running
- **THEN** 34B SHALL wait until 34A completes or stops