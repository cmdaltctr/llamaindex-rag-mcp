"""Document loading, chunking, and indexing into ChromaDB."""

from pathlib import Path

import chromadb
from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    SUPPORTED_EXTENSIONS,
)


def _get_chroma_collection():
    """Return (or create) the ChromaDB collection used for storing vectors."""
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return db.get_or_create_collection(COLLECTION_NAME)


def ingest_path(path: str) -> dict:
    """Index a single file or an entire directory into the RAG vector store.

    Args:
        path: Absolute or relative path to a file or directory.

    Returns:
        A dict with one of two shapes:
        - success: {"status": "ok", "files_indexed": N, "chunks_created": M}
        - error:   {"status": "error", "message": "..."}
    """
    path_obj = Path(path)
    if not path_obj.exists():
        return {"status": "error", "message": f"Path not found: {path}"}

    # Gather supported files ------------------------------------------------
    files_to_index: list[Path] = []
    if path_obj.is_file():
        if path_obj.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return {
                "status": "error",
                "message": (
                    f"Unsupported file extension: {path_obj.suffix}. "
                    f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                ),
            }
        files_to_index.append(path_obj)
    else:
        for ext in SUPPORTED_EXTENSIONS:
            files_to_index.extend(path_obj.rglob(f"*{ext}"))

    if not files_to_index:
        return {"status": "ok", "files_indexed": 0, "chunks_created": 0}

    # Load & chunk -----------------------------------------------------------
    reader = SimpleDirectoryReader(
        input_files=[str(f) for f in files_to_index],
        filename_as_id=True,
    )
    documents = reader.load_data()

    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = splitter.get_nodes_from_documents(documents)

    # Persist to ChromaDB ----------------------------------------------------
    collection = _get_chroma_collection()
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        show_progress=False,
    )

    return {
        "status": "ok",
        "files_indexed": len(files_to_index),
        "chunks_created": len(nodes),
    }


def list_documents() -> list[dict]:
    """Return unique source file paths and their chunk counts from the index.

    Each entry: {"source": str, "chunks": int}
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        collection = db.get_collection(COLLECTION_NAME)
    except Exception:
        return []  # collection hasn't been created yet

    count = collection.count()
    if count == 0:
        return []

    # Fetch everything so we can group by source file
    all_data = collection.get(include=["metadatas"])
    source_counts: dict[str, int] = {}
    for meta in all_data["metadatas"]:
        if meta is None:
            continue
        source = meta.get("file_path") or meta.get("file_name") or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

    return [
        {"source": src, "chunks": cnt}
        for src, cnt in sorted(source_counts.items())
    ]
