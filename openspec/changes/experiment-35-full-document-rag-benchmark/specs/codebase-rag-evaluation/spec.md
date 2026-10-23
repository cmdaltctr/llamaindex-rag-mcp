# codebase-rag-evaluation Specification

## ADDED Requirements

### Requirement: Codebase baseline uses a frozen RepoProbe subset

Experiment 35B-1 SHALL evaluate answers from the current OMRS `codebase` profile on a small frozen RepoProbe subset, scored with the RepoProbe checklist scorer and a frozen judge. The report SHALL label the result as single-shot RAG and SHALL NOT compare it with agent results from the RepoProbe paper.

#### Scenario: RepoProbe result is compared with agent scores
- **WHEN** the report places the 35B-1 score beside agent scores from the RepoProbe paper
- **THEN** it SHALL state that RepoProbe evaluated tool-using agents and OMRS answered from one retrieval pass
- **AND** it SHALL NOT present the two as a like-for-like comparison

#### Scenario: Repository identity is not pinned
- **WHEN** a repository does not have a frozen commit SHA or equivalent immutable identity
- **THEN** it SHALL NOT be included in the measured 35B baseline

### Requirement: Codebase baseline uses the shipped codebase profile

The measured run SHALL preserve the current codebase retrieval policy, including hybrid retrieval and the profile's reranker setting.

#### Scenario: Document reranking is enabled only for the benchmark
- **WHEN** reranking is enabled contrary to the frozen codebase profile
- **THEN** the run SHALL be labelled exploratory
- **AND** it SHALL NOT replace the 35B baseline

### Requirement: Codebase retrieval is measured on a labelled set

Experiment 35B-2 SHALL measure codebase retrieval with Recall@K and MRR@10 on the frozen FreshStack LangChain slice, all 223 queries, through a new index built with the frozen `codebase` profile. Retrieval metrics SHALL NOT be computed from RepoProbe, because RepoProbe labels no gold files or chunks. Each retrieved chunk SHALL be mapped to its parent document, and only the first rank of each parent SHALL count. An earlier FreshStack run MAY be reported beside the baseline as a reference, and the report SHALL name the settings that differ.

#### Scenario: Retrieval metrics are requested for RepoProbe
- **WHEN** the harness is asked for Recall@K on a RepoProbe question
- **THEN** it SHALL report the metric as not measurable for that benchmark

#### Scenario: An earlier run is reported as a reference
- **WHEN** the report shows Experiment 22 beside the 35B-2 result
- **THEN** it SHALL label Experiment 22 as a reference, not the baseline
- **AND** it SHALL list the settings that differ, such as top_k, chunking fallback and embedding model

#### Scenario: Several chunks from one document are retrieved
- **WHEN** three chunks of the same parent document appear in the top 10
- **THEN** Recall@10 SHALL count that parent once, at the rank of its first chunk

#### Scenario: The RepoProbe judge runs at its default effort
- **WHEN** the 35B-1 judge config omits `reasoning_effort` for GLM-5.3
- **THEN** the run SHALL be labelled exploratory, because GLM-5.3 defaults to `max` and the frozen setting is `low`

### Requirement: Codebase retrieval and answer quality are reported separately

The benchmark SHALL preserve retrieval-stage evidence (35B-2) separately from final answer scoring (35B-1).

#### Scenario: The final answer is wrong despite retrieving the correct source
- **WHEN** the gold evidence of a 35B-2 question is present in the retrieved set
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

The first 35B baseline SHALL use only the approved small subset and SHALL run separately from 35A.

#### Scenario: Both profiles are scheduled concurrently on the Mac
- **WHEN** 35A is still running
- **THEN** 35B SHALL wait until 35A completes or stops