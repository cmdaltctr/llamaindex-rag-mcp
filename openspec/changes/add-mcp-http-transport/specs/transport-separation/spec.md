# transport-separation delta

## MODIFIED Requirements

### Requirement: FastMCP lifespan and context forward-compatibility

`transports/mcp/` SHALL build the MCP server through a factory that takes a lifespan and registers every tool on the new server. The lifespan SHALL yield a context holding the Engine and the path policy for that transport, and every tool handler SHALL read them from its request context (`ctx: Context`). Tool handlers SHALL NOT read the process-default store, settings, reranker or profile resolver. The stdio entry point SHALL build its Engine inside the lifespan through `compose.build_engine()` and close it when the lifespan exits.

#### Scenario: Lifespan slot preserved

- **WHEN** the MCP server factory is inspected
- **THEN** it MUST accept a lifespan, and the stdio and HTTP transports MUST each pass their own

#### Scenario: Context parameter not precluded

- **WHEN** tool handler signatures are inspected
- **THEN** each handler MUST take `ctx: Context` and MUST obtain the Engine from it

#### Scenario: No process defaults

- **WHEN** the stdio server runs a search with the process-default store left unset
- **THEN** the search MUST succeed using the lifespan's Engine
