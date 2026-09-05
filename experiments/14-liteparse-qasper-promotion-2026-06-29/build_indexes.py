"""Build indexes for Experiment 14: LiteParse vs pypdf on Qasper.

D19 repair (Stage 4 task 4.3.6, protocol v2.0): the build path reads real
immutable PDF bytes — ``sorted(corpus_dir.glob("*.pdf"))`` — parses them
through the production factory ``get_pdf_reader(reader)``, and records a
chronological parse-event log plus a per-parser parsed-text artefact whose
identity is its sha256, BEFORE any embedding is computed.  Preflight
(:func:`preflight_check`) proves the parser was invoked before embeddings
and aborts the build otherwise; ``--skip-embed`` writes the artefact and
preflight manifest only (agreement tests and dry runs touch no Ollama).

Ingestion time is decomposed into ``parse_time_s_total`` and
``embed_write_time_s`` so a faster parser cannot hide behind the dominant
embedding stage; ``ingestion_time_s`` (their sum) is retained for the v1
summariser's H2 gate.  Each parser gets its own index through
``experiment_storage_config(parser=...)`` — the reader is part of the
collection identity because parsed text differs between readers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

PLAN_PATH = SCRIPT_DIR / "plan.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
EXPERIMENT_ID = "14-liteparse-qasper-promotion"
PROTOCOL_VERSION = "2.1"


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the three build cells as plan-comparable dicts (D15 generator).

    Agreement tests compare these against the ``build_*`` cells declared in
    ``plan.json`` via ``ExperimentPlan.assert_runner_cells``.
    Protocol v2.1 (2026-08-23): pdf_inspector joins as the third reader.
    """
    return [
        {"id": "build_pypdf", "factors": {"reader": "pypdf"}},
        {"id": "build_liteparse", "factors": {"reader": "liteparse"}},
        {"id": "build_pdf_inspector", "factors": {"reader": "pdf_inspector"}},
    ]


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str) -> None:
        import requests

        self.model = model
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            resp = self._session.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                results.append(embeddings[0])
            else:
                results.append([])
        return results


def _sha256_hex(data: bytes) -> str:
    """Return the plain hex sha256 digest of *data* (no prefix)."""
    return hashlib.sha256(data).hexdigest()


def corpus_identity(corpus_dir: Path) -> dict[str, Any]:
    """Return the immutable content identity of a PDF corpus directory.

    The identity is the sha256 of the concatenation of the sorted per-file
    hex digests, so adding, removing or editing any PDF produces a new
    corpus identity (D19: files are immutable inputs).

    Args:
        corpus_dir: Directory containing the corpus ``*.pdf`` files.

    Returns:
        ``{"files": [...], "sha256_by_file": {...}, "corpus_sha256":
        "sha256:<hex>"}`` with file names sorted.
    """
    pdf_files = sorted(corpus_dir.glob("*.pdf"))
    sha_by_file = {path.name: _sha256_hex(path.read_bytes()) for path in pdf_files}
    concatenated = "".join(sha_by_file[name] for name in sorted(sha_by_file)).encode("utf-8")
    return {
        "files": [path.name for path in pdf_files],
        "sha256_by_file": sha_by_file,
        "corpus_sha256": f"sha256:{_sha256_hex(concatenated)}",
    }


def artefact_identity(parsed_documents: list[dict[str, Any]]) -> str:
    """Return the sha256 identity of a parser-output artefact.

    The identity covers the full JSON-serialised ``parsed_documents`` list
    (sorted keys), so distinct parsers producing different text MUST yield
    distinct artefact identities — this is the D19 parser-output identity.
    """
    payload = json.dumps(parsed_documents, sort_keys=True, ensure_ascii=False)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _source_page_count(pdf_path: Path) -> int:
    """Return the number of physical pages in a source PDF."""
    from pypdf import PdfReader

    return len(PdfReader(pdf_path).pages)


def _token_count(text: str) -> int:
    """Return the LlamaIndex-default token count for parsed text."""
    from llama_index.core.utilities.token_counting import TokenCounter

    return TokenCounter().get_string_tokens(text)


def parse_corpus(corpus_dir: Path, reader: str) -> dict[str, Any]:
    """Parse every PDF through the production reader factory (D19 parse stage).

    The adapter is resolved exactly once via ``get_pdf_reader(reader)`` —
    the harness never imports a parser directly.  Each file gets a
    chronological ``parse_start``/``parse_end`` event pair (plus
    ``parse_error`` on failure); a parse failure does NOT abort the build:
    the file is recorded with empty text and the error string.

    Args:
        corpus_dir: Directory containing the corpus ``*.pdf`` files.
        reader: Reader name from ``--reader`` (``pypdf`` or ``liteparse``).

    Returns:
        A dict with ``reader``, ``corpus_identity``, ``events``,
        ``parsed_documents`` (one record per file: file, source_sha256,
        text, char_count, source_page_count, emitted_document_count,
        token_count, parse_time_s, error), ``parsed_text_sha256_by_file``
        and ``artefact_sha256``.
    """
    from omrg.integrations.pdf.factory import get_pdf_reader

    identity = corpus_identity(corpus_dir)
    adapter = get_pdf_reader(reader)
    events: list[dict[str, Any]] = []
    parsed_documents: list[dict[str, Any]] = []
    parsed_text_sha256_by_file: dict[str, str] = {}

    for pdf_path in sorted(corpus_dir.glob("*.pdf")):
        source_sha256 = _sha256_hex(pdf_path.read_bytes())
        events.append(
            {
                "event": "parse_start",
                "parser": reader,
                "file": pdf_path.name,
                "timestamp": time.perf_counter(),
            }
        )
        text = ""
        source_page_count: int | None = None
        emitted_document_count: int | None = None
        token_count: int | None = None
        error: str | None = None
        start = time.perf_counter()
        try:
            documents = adapter.load_data(pdf_path)
            text = "\n".join(document.text for document in documents)
        except Exception as exc:  # a parse failure is recorded data, not a crash
            error = str(exc)
            events.append(
                {
                    "event": "parse_error",
                    "parser": reader,
                    "file": pdf_path.name,
                    "error": error,
                    "timestamp": time.perf_counter(),
                }
            )
        parse_time_s = time.perf_counter() - start
        token_count = _token_count(text)
        if error is None:
            source_page_count = _source_page_count(pdf_path)
            emitted_document_count = len(documents)
        events.append(
            {
                "event": "parse_end",
                "parser": reader,
                "file": pdf_path.name,
                "timestamp": time.perf_counter(),
            }
        )
        parsed_documents.append(
            {
                "file": pdf_path.name,
                "source_sha256": source_sha256,
                "text": text,
                "char_count": len(text),
                "source_page_count": source_page_count,
                "emitted_document_count": emitted_document_count,
                "token_count": token_count,
                "parse_time_s": parse_time_s,
                "error": error,
            }
        )
        parsed_text_sha256_by_file[pdf_path.name] = _sha256_hex(text.encode("utf-8"))

    return {
        "reader": reader,
        "corpus_identity": identity,
        "events": events,
        "parsed_documents": parsed_documents,
        "parsed_text_sha256_by_file": parsed_text_sha256_by_file,
        "artefact_sha256": artefact_identity(parsed_documents),
    }


def write_parsed_artefact(out_dir: Path, reader: str, parse_result: dict[str, Any]) -> Path:
    """Atomically write the per-parser parsed-text artefact (``.tmp`` rename).

    Args:
        out_dir: Output directory (created when absent).
        reader: Reader name, used in the ``parsed_<reader>.json`` filename.
        parse_result: Full result of :func:`parse_corpus`.

    Returns:
        The final artefact path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"parsed_{reader}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(parse_result, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(path)
    return path


def _plan_preflight_assertions() -> list[dict[str, Any]]:
    """Load the preflight assertions from the machine-readable plan (D15)."""
    payload = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    return [dict(item) for item in payload.get("preflight_assertions", [])]


def preflight_check(
    parse_result: dict[str, Any],
    *,
    embed_model: str | None = None,
    index_identity: str | None = None,
    assertions: list[dict[str, Any]] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build the runtime manifest and run D14/D19 preflight on the parse stage.

    Runs before the embed stage in :func:`main`: the event log must prove
    the declared parser was invoked before any embedding, the manifest must
    show no backend fallback, and every plan assertion must hold.

    Args:
        parse_result: Full result of :func:`parse_corpus`.
        embed_model: Embedding model for the manifest block; defaults to
            the ``EMBED_MODEL`` environment variable (None leaves the
            block's model null with a recorded reason — acceptable for
            ``--skip-embed`` dry runs).
        index_identity: Immutable index identity from
            ``experiment_storage_config``; None for dry runs without
            storage.
        assertions: Plan preflight assertions; defaults to
            ``plan.json``'s ``preflight_assertions``.
        project_root: Repository root for git/lock facts (injectable for
            tests); defaults to this repository.

    Returns:
        The validated runtime manifest.

    Raises:
        PreflightError: Propagates from any failed assertion — the build
            aborts rather than embedding from an unproven parse stage.
    """
    from experiments._lib.manifest import build_runtime_manifest
    from experiments._lib.preflight import (
        assert_manifest,
        assert_no_fallback,
        assert_parser_invoked_before_embeddings,
    )

    reader = str(parse_result["reader"])
    model = embed_model if embed_model is not None else os.getenv("EMBED_MODEL")
    manifest = build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        embedding={"requested_provider": "ollama", "effective_provider": "ollama", "model": model},
        document_backend={"requested": reader, "effective": reader},
        index_identity=index_identity,
        project_root=project_root if project_root is not None else PROJECT_ROOT,
        extra={
            "corpus_identity": parse_result["corpus_identity"]["corpus_sha256"],
            "artefact_identity": parse_result["artefact_sha256"],
        },
    )
    # The corpus identity here is directory-level, not one hashed file, so
    # it arrives via ``extra``; drop the stale "corpus_path not provided"
    # null reason the single-path parameter left behind.
    manifest["null_reasons"].pop("corpus_identity", None)

    assert_parser_invoked_before_embeddings(parse_result["events"], [reader])
    assert_no_fallback(manifest)
    assert_manifest(
        manifest,
        assertions if assertions is not None else _plan_preflight_assertions(),
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Experiment 14 indexes (D19 v2.0)")
    parser.add_argument("--reader", choices=["pypdf", "liteparse", "pdf_inspector"], required=True)
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=SCRIPT_DIR / "qasper_pdfs",
        help="Directory of immutable PDF inputs (default: qasper_pdfs/; the "
        "fixtures/ dir works for dry runs and agreement tests)",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Write the parsed artefact and preflight manifest only — no "
        "Ollama, no Chroma store (used by agreement tests and dry runs)",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    # The liteparse reader resolves the composition-root default
    # EffectiveSettings (ADR-037); no entry point imported compose, so
    # install it explicitly.  Deliberately NOT ensure_runtime_setup():
    # that would build the ambient .env store and embed model, overriding
    # the per-parser experiment store built below.
    from omrg.compose import settings_to_effective
    from omrg.config import get_settings
    from omrg.core.settings import set_default_effective_settings

    set_default_effective_settings(settings_to_effective(get_settings()))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    corpus_dir = args.corpus_dir
    if not corpus_dir.exists():
        raise SystemExit(
            f"Corpus directory not found: {corpus_dir}. Run prepare_qasper_pdfs.py "
            "first or pass --corpus-dir (the fixtures dir works for dry runs)."
        )

    # Harmless for ambient settings, but the parse path never relies on it:
    # parsing goes through get_pdf_reader(args.reader) directly.
    os.environ["PDF_READER"] = args.reader

    print(f"[parse] reader={args.reader} corpus={corpus_dir}", flush=True)
    parse_result = parse_corpus(corpus_dir, args.reader)
    errors = [doc["file"] for doc in parse_result["parsed_documents"] if doc["error"]]
    total_chars = sum(doc["char_count"] for doc in parse_result["parsed_documents"])
    print(
        f"[parse] {len(parse_result['parsed_documents'])} files, {total_chars} chars, "
        f"{len(errors)} parse errors; artefact {parse_result['artefact_sha256']}",
        flush=True,
    )

    artefact_path = write_parsed_artefact(OUTPUT_DIR, args.reader, parse_result)
    print(f"[parse] artefact written: {artefact_path}", flush=True)

    if args.skip_embed:
        manifest = preflight_check(parse_result)
        manifest_path = OUTPUT_DIR / f"preflight_manifest_{args.reader}.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[preflight] manifest written: {manifest_path}", flush=True)
        return

    embed_model = os.getenv("EMBED_MODEL")
    if not embed_model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    from experiments._lib.storage import experiment_storage_config

    chroma_dir = str(OUTPUT_DIR / f"chroma_{args.reader}")
    storage = experiment_storage_config(
        experiment_id="exp14",
        corpus="qasper",
        provider="ollama",
        model=embed_model,
        parser=args.reader,
        persist_dir=chroma_dir,
    )

    # D19: preflight aborts before the embed stage, not after it.
    manifest = preflight_check(
        parse_result,
        embed_model=embed_model,
        index_identity=storage.collection_name,
    )
    print(f"[preflight] ok; index identity {storage.collection_name}", flush=True)

    documents = parse_result["parsed_documents"]
    print(f"Embedding with {embed_model} (reader={args.reader})...", flush=True)
    embedder = OllamaEmbedder(embed_model, ollama_url)

    batch_size = int(os.getenv("EMBED_BATCH_SIZE", "50"))
    all_embeddings: list[list[float]] = []
    embed_write_start = time.perf_counter()
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        embs = embedder.embed([doc["text"] for doc in batch])
        all_embeddings.extend(embs)
        print(f"  Embedded {i + len(batch)}/{len(documents)}", flush=True)

    # Store through the production vector-store path (local or cloud).
    print(f"Storing in ChromaDB (reader={args.reader})...", flush=True)
    collection_name = storage.collection_name
    store = storage.build_store()
    row_ids = [Path(doc["file"]).stem for doc in documents]
    metadatas = [
        {
            "id": Path(doc["file"]).stem,
            "reader": args.reader,
            "source_sha256": doc["source_sha256"],
        }
        for doc in documents
    ]
    from omrg.core.vectordb.identity import EmbeddingIdentity
    from omrg.core.vectordb.validation import validate_embedding_batch

    identity = EmbeddingIdentity(provider="ollama", model=embed_model)
    validate_embedding_batch(
        row_ids,
        all_embeddings,
        collection_name=collection_name,
        embedding_identity=identity,
        existing_dimension=store.get_collection_dimension(collection_name),
    )
    if store.collection_exists(collection_name):
        store.delete_collection(collection_name)
    store.create_collection(collection_name)

    store.upsert_precomputed(
        collection_name,
        ids=row_ids,
        documents=[doc["text"] for doc in documents],
        embeddings=all_embeddings,
        metadatas=metadatas,
        embedding_identity=identity,
    )
    embed_write_time_s = time.perf_counter() - embed_write_start

    parse_time_s_total = sum(doc["parse_time_s"] for doc in documents)
    print(
        f"Stored {len(documents)} documents. parse={parse_time_s_total:.1f}s "
        f"embed+write={embed_write_time_s:.1f}s",
        flush=True,
    )
    print(f"Collection: {collection_name}", flush=True)

    build_info = {
        "built_at_unix": time.time(),
        "reader": args.reader,
        "embed_model": embed_model,
        "total_docs": len(documents),
        "corpus_identity": parse_result["corpus_identity"],
        "artefact_identity": parse_result["artefact_sha256"],
        "parse_time_s_total": round(parse_time_s_total, 2),
        "embed_write_time_s": round(embed_write_time_s, 2),
        # Retained total for the v1 summariser's H2 speed gate; the D19
        # decomposition is the two fields above.
        "ingestion_time_s": round(parse_time_s_total + embed_write_time_s, 2),
        "chroma_dir": chroma_dir,
        "preflight_manifest": manifest,
    }
    (OUTPUT_DIR / f"index_build_{args.reader}.json").write_text(
        json.dumps(build_info, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("Index build metadata written", flush=True)


if __name__ == "__main__":
    main()
