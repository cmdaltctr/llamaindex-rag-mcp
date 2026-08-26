Immutable tiny-fixture PDFs for the D19 build-path tests.

- Provenance: copied byte-identical from `tests/fixtures/pdf_dir/`
  (doc1_climate.pdf, doc2_quantum.pdf); never edit them here.
- Immutability rule: these bytes are frozen inputs; identity is their
  sha256 (`sha256_by_file` in every parsed artefact).
- Purpose: `tests/test_experiment_14_harness.py` parses them with pypdf
  (deterministic per AGENTS.md gotcha 6) to prove the build path reads
  real PDF bytes through `get_pdf_reader` — no Ollama, no network.
