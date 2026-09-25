# Spec Delta

## Purpose

Remove markup noise from text that PDF readers and OCR engines emit, before the text is chunked and embedded. Stored chunks then carry document text, not formatting tags or image placeholders, whichever engine produced them.

## ADDED Requirements

### Requirement: Reader output from PDF sources SHALL be normalised before chunking

When normalisation is enabled, the ingestion pipeline SHALL normalise the text of every document read from a PDF source before chunking. This covers every PDF reader, OCR tier and cloud document backend. Normalisation SHALL be deterministic: the same input text SHALL always give the same output text. It SHALL NOT call a language model or any network service.

Text from authored files (`.md`, `.txt`, `.html` and other non-PDF document sources) and from code and config files SHALL pass through unchanged.

#### Scenario: PDF-derived text is normalised

- **GIVEN** normalisation is enabled
- **WHEN** a PDF is ingested and its reader emits `<u>ARTICLE HEADER</u>` in the page text
- **THEN** the stored chunk text SHALL contain `ARTICLE HEADER`
- **AND** it SHALL NOT contain `<u>` or `</u>`

#### Scenario: Authored Markdown keeps its HTML

- **GIVEN** normalisation is enabled
- **WHEN** a `.md` file containing `<div align="center"><img src="logo.png"></div>` is ingested
- **THEN** the stored chunk text SHALL contain that markup unchanged

#### Scenario: Normalisation is deterministic

- **WHEN** the same reader output is normalised twice
- **THEN** both results SHALL be identical

### Requirement: Formatting-only tags SHALL be removed and their text kept

Normalisation SHALL remove the tags `<u>`, `<span>`, `<font>` and `<center>` and keep their inner text. It SHALL convert `<b>` and `<strong>` to Markdown bold (`**text**`) and `<i>` and `<em>` to Markdown italic (`*text*`). It SHALL convert `<br>` to a line break. The rule list SHALL be closed: a tag not named in this capability SHALL pass through unchanged.

#### Scenario: Underline around a sentence fragment

- **WHEN** the reader emits `signifi- <u>cantly different at p≤ 0.05</u>`
- **THEN** the normalised text SHALL be `signifi- cantly different at p≤ 0.05`

#### Scenario: Bold tag becomes Markdown bold

- **WHEN** the reader emits `<b>Fig 4.</b> Changes in chlorophyll`
- **THEN** the normalised text SHALL be `**Fig 4.** Changes in chlorophyll`

#### Scenario: Unknown tag passes through

- **WHEN** the reader emits `H<sub>2</sub>O`
- **THEN** the normalised text SHALL be `H<sub>2</sub>O`

### Requirement: Blocks SHALL be unwrapped and image tags removed

Normalisation SHALL remove the tags of every `<div>` block and keep the block's text, whether or not the block contains an `<img>`. Text an engine recognised inside a picture (a badge, an advertisement, chart labels) is document text. Normalisation SHALL remove every `<img>` tag. It SHALL NOT insert a placeholder where an image was.

#### Scenario: Text inside an image block is kept

- **WHEN** the reader emits `<div style="text-align: center;"><img src="imgs/a.jpg" alt="Image" />Check for updates</div>`
- **THEN** the normalised text SHALL contain `Check for updates`
- **AND** it SHALL NOT contain `<div` or `<img`

#### Scenario: An image-only block leaves no placeholder

- **WHEN** the reader emits `before<div><img src="imgs/c.jpg" alt="Image" /></div>after`
- **THEN** the normalised text SHALL be `beforeafter`

#### Scenario: Figure caption in a text-only block is kept

- **WHEN** the reader emits `<div style="text-align: center;">FIGURE 2 Statistical description of scoliosis-related genes</div>`
- **THEN** the normalised text SHALL contain `FIGURE 2 Statistical description of scoliosis-related genes`
- **AND** it SHALL NOT contain `<div`

#### Scenario: Bare image tag is removed

- **WHEN** the reader emits a line `<img src="imgs/b.jpg" alt="Image" width="8%" />`
- **THEN** the normalised text SHALL NOT contain `<img`

### Requirement: Links, tables, code and maths SHALL be preserved

Normalisation SHALL keep Markdown links and bare URLs unchanged. It SHALL keep `<table>` blocks as HTML tables. Inside a table it SHALL keep only the `table`, `thead`, `tbody`, `tr`, `td` and `th` tags and their `colspan` and `rowspan` attributes, and SHALL remove every other attribute. It SHALL decode HTML entities outside tables, code and maths. It SHALL NOT change fenced code blocks or inline code spans. It SHALL NOT change LaTeX maths: `$…$` within one line, `$$…$$`, and `\begin{…}…\end{…}` with matching environment names.

#### Scenario: Link is untouched

- **WHEN** the reader emits `[https://doi.org/10.1371/x](https://doi.org/10.1371/x)`
- **THEN** the normalised text SHALL be identical to the input

#### Scenario: Table keeps structure and loses presentation

- **WHEN** the reader emits `<table border=1 style='margin: auto;'><tr><td colspan="2" style='text-align: center;'>Rigid propeller</td></tr></table>`
- **THEN** the normalised text SHALL be `<table><tr><td colspan="2">Rigid propeller</td></tr></table>`

#### Scenario: Code fence is untouched

- **WHEN** the reader emits a fenced code block that contains `<div>` and `&amp;`
- **THEN** the fenced block SHALL be identical in the normalised text

#### Scenario: Aligned maths is untouched

- **WHEN** the reader emits `$$ \begin{align*} f(x) &= a < b \\ &not= c &times d \end{align*} $$`
- **THEN** the maths block SHALL be identical in the normalised text
- **AND** it SHALL NOT contain `¬` or `×` (`html.unescape` would decode `&not` and `&times` without a semicolon)

### Requirement: Normalisation SHALL NOT lose document text

Every visible character of the input SHALL appear in the normalised output, including text inside image blocks. Visible characters are those outside tags, after entity decoding.

#### Scenario: Visible text survives on the Experiment 34 outputs

- **WHEN** the normaliser runs over the Experiment 34 outputs of pdf-inspector, LiteParse, the local OCR tier, the OCR worker and dots.mocr
- **THEN** the visible-character count of each page SHALL be equal before and after normalisation

### Requirement: Normalisation SHALL be configurable

The setting `ingestion.normalise_reader_output` (environment variable `INGESTION__NORMALISE_READER_OUTPUT`) SHALL turn normalisation on or off. The default SHALL be on. When it is off, reader output SHALL reach the chunker unchanged.

#### Scenario: Disabled normalisation keeps raw output

- **GIVEN** `INGESTION__NORMALISE_READER_OUTPUT=false`
- **WHEN** a PDF whose reader emits `<u>header</u>` is ingested
- **THEN** the stored chunk text SHALL contain `<u>header</u>`
