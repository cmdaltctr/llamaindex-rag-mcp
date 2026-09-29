## ADDED Requirements

### Requirement: LiteParse adapter SHALL emit multi-column pages in reading order

The LiteParse adapter SHALL classify each page's layout from its own text items before joining them into text. A page classified `multi_column` SHALL be joined column by column: every item of the first column in vertical order, then every item of the next column. A page not classified `multi_column` SHALL keep the order the library returned, so single-column pages, tables and layouts the classifier does not recognise are unchanged, and SHALL keep the `column` label the adapter emits today.

Classification SHALL depend only on the geometry of the page's own text items and SHALL NOT read the document, the file name or any setting. It SHALL require a vertical gutter: a band of the page's horizontal extent that the page's own non-full-width items leave essentially uncovered, whose centre lies in the middle third of that extent, with text on both sides of comparable quantity, each side spanning most of the page's vertical text extent. A page that fails any of those conditions SHALL keep the library order and SHALL NOT be labelled `multi_column`.

Reordering SHALL NOT add, drop or alter any item. Together with the line join below, the only change to a page's characters SHALL be whitespace.

#### Scenario: Two-column body page is emitted column by column

- **GIVEN** a page whose text items form two columns separated by a gutter
- **WHEN** the adapter emits its Document
- **THEN** the text SHALL contain every item of the left column, in vertical order, before any item of the right column

#### Scenario: Single-column page keeps the library order

- **GIVEN** a page whose items leave no qualifying gutter
- **WHEN** the adapter emits its Document
- **THEN** the text SHALL be the items joined in the order LiteParse returned them

#### Scenario: A table is not reordered

- **GIVEN** a page whose items are laid out in rows across the page with no qualifying gutter
- **WHEN** the adapter emits its Document
- **THEN** the item order SHALL be unchanged
- **AND** the page SHALL NOT be labelled `multi_column`

#### Scenario: Reordering preserves content

- **GIVEN** any page the adapter reorders
- **WHEN** the adapter emits its Document
- **THEN** the multiset of item texts in the output SHALL equal the multiset LiteParse returned

### Requirement: LiteParse adapter SHALL join the items of one visual line

The adapter SHALL join consecutive items that sit on one visual line, left to right, into one line of text. Two items share a line when their vertical ranges overlap by at least half the shorter item's height and the second starts at or to the right of the first. Items on one line SHALL be joined by a single space, or by no space when the horizontal gap is under one tenth of the shorter height (a kerning split). A gap wider than the taller item's height SHALL start a new line, so a sidebar and the body beside it are never joined. Every other item boundary SHALL be a line break. The join SHALL NOT change item order or item text.

#### Scenario: Words drawn separately form one line

- **GIVEN** a title whose words are separate items at the same height
- **WHEN** the adapter emits its Document
- **THEN** the title SHALL be one line, its words separated by single spaces

#### Scenario: A column gap breaks the line

- **GIVEN** two items at the same height separated by more than one text height
- **WHEN** the adapter emits its Document
- **THEN** they SHALL be on separate lines

#### Scenario: A kerning split rejoins without a space

- **GIVEN** two pieces of one word with no gap between them
- **WHEN** the adapter emits its Document
- **THEN** they SHALL be joined with no space

## MODIFIED Requirements

### Requirement: LiteParse adapter SHALL capture bounding-box metadata on emitted Documents

When the LiteParse adapter is in use, every emitted `Document` object SHALL carry a `metadata` dictionary containing spatial information extracted by LiteParse. The metadata SHALL include the keys `pdf_reader="liteparse"`, `page=<int>` (1-indexed), `column=<"left"|"right"|"single"|"multi_column">`, `section_bbox=<[x0, y0, x1, y1]>` (page-coordinate space), and `bbox_schema_version=1`. A page the adapter joins column by column SHALL carry `column="multi_column"`, so the label names the order the text is in. Retrieval-side consumption of these fields is out of scope for this change.

#### Scenario: Two-column academic PDF
- **WHEN** a two-column academic PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document for a page joined column by column SHALL have `metadata["column"]` set to `"multi_column"`
- **AND** a two-column page the classifier does not recognise SHALL keep `"left"` or `"right"`
- **AND** `metadata["page"]` SHALL reflect the 1-indexed source page number

#### Scenario: Single-column PDF
- **WHEN** a single-column PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document SHALL have `metadata["column"]` set to `"single"`

#### Scenario: Non-LiteParse readers do not emit bbox fields
- **WHEN** a PDF is ingested via the pypdf or pypdfium2 adapter
- **THEN** emitted Documents SHALL NOT carry `section_bbox`, `column`, or `bbox_schema_version` keys (these are LiteParse-specific)
- **AND** `metadata["pdf_reader"]` SHALL be set to the backend name (`"pypdf"` or `"pypdfium2"`) for diagnostics
