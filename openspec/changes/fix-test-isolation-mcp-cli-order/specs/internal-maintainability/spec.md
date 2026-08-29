## ADDED Requirements

### Requirement: Test modules restore logging state they install

Test modules SHALL NOT leave logging handlers, levels, or stream bindings
installed after their tests complete when that configuration was added or
replaced during the module's execution. CLI tests that parse command output
as JSON SHALL receive output uncontaminated by logging-machinery error
banners regardless of which test module ran earlier in the same session.

#### Scenario: MCP tool tests precede a CLI JSON test

- **WHEN** pytest executes `tests/test_mcp_tools.py` immediately before
  `tests/test_cli.py::TestIngestCLI::test_ingest_json_output`
- **THEN** `json.loads(result.output)` succeeds
- **AND** the captured output contains no `--- Logging error ---` banner

#### Scenario: Isolation behaviour is unchanged

- **WHEN** the CLI JSON test runs alone
- **THEN** it passes exactly as before the fix

#### Scenario: A test module reconfigures logging

- **WHEN** a test module adds or replaces root logging handlers during its
  execution
- **THEN** teardown restores the handler and level configuration that existed
  before the module ran
