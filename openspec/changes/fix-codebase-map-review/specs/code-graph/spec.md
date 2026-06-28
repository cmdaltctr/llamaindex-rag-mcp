## MODIFIED Requirements

### Requirement: NetworkX directed graph construction

The system SHALL build a `networkx.DiGraph` where nodes represent files and edges represent structural relationships (imports, inheritance, calls). Each node SHALL carry metadata: `type` (literal `"file"`), `content_type` (Magika label, e.g., `code/typescript`), `functions` (list of defined function names), `imports` (list of imported file paths), `classes` (list of class names), `exports` (list of exported symbol names), and `inheritance` (list of `(child, parent)` tuples from AST extraction). Inheritance edges SHALL be constructed by reading the `inheritance` list from each node and creating edges to files containing the parent class.

#### Scenario: Node metadata

- **WHEN** `src/auth/login.ts` is added to the graph
- **THEN** the node SHALL have `type="file"`, `content_type="code/typescript"`, and lists of functions, imports, classes, exports, and inheritance extracted by tree-sitter

#### Scenario: Edge metadata

- **WHEN** an import relationship is detected from `login.ts` to `session.ts`
- **THEN** the edge SHALL have `relation="import"` and `confidence="exact"`

#### Scenario: Self-import ignored

- **WHEN** a file imports itself (circular or re-export)
- **THEN** no self-loop edge SHALL be added to the graph

#### Scenario: Inheritance edge created

- **WHEN** `models.py` contains `class Admin(User):` and `user.py` contains `class User:`
- **THEN** an edge SHALL be added from `models.py` to `user.py` with `relation="inheritance"` and `confidence="exact"`

#### Scenario: Inheritance edge to missing parent

- **WHEN** `models.py` contains `class Admin(BaseModel):` and no file in the project contains `class BaseModel:`
- **THEN** no inheritance edge SHALL be added (parent class not found in any file)
