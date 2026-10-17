# Spec Delta

## ADDED Requirements

### Requirement: Profile requests create no run records

A search, answer or ingestion that runs a user profile's pipeline for Chat, Knowledge Base search, an MCP tool or an ingestion job SHALL run within that request. It SHALL NOT enter the run queue and SHALL NOT write a run record or run events. A run started from Studio SHALL keep creating a run record.

#### Scenario: Chat question on a user profile

- **WHEN** a user asks a question in Chat about a collection that uses a user profile
- **THEN** the run list MUST stay unchanged

#### Scenario: Studio run of a slot pipeline

- **WHEN** a user runs the Search pipeline of a user profile from Studio
- **THEN** the workspace MUST record that run with its revision, as for any other Studio run
