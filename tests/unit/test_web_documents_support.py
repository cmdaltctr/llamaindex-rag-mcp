"""Shared helpers for the web document and destructive-action tests.

Not a test module: it holds the app factory, the session login, a real
store seeder with full chunk lineage, a recording Engine, and the
OpenAPI response-schema checker. No model, LLM or network call happens.
"""

from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

import jsonschema  # noqa: E402
import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from llama_index.core.embeddings import MockEmbedding  # noqa: E402

from omrg.core.ingestion.source_state import (  # noqa: E402
    build_source_id,
    canonical_source_path,
)
from omrg.core.vectordb.base import VectorStore  # noqa: E402
from omrg.core.vectordb.identity import EmbeddingIdentity  # noqa: E402
from omrg.core.vectordb.lancedb.store import LanceVectorStore  # noqa: E402
from omrg.engine import Engine  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402

BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}
OPENAPI = (
    Path(__file__).resolve().parents[2] / "src" / "omrg" / "transports" / "api" / "openapi.yaml"
)
_IDENTITY = EmbeddingIdentity(provider="test", model="mock")

#: Response keys the runtime returns that ``openapi.yaml`` does not declare.
#: Task 6.7 declared them all, so every entry is empty. Keep it empty.
PENDING_CONTRACT_KEYS: dict[str, frozenset[str]] = {
    "DeleteResult": frozenset(),
    "ProfilePreview": frozenset(),
}


# ── Stores and engines ───────────────────────────────────────────────────


def lance_store(tmp_path: Path) -> VectorStore:
    """Return an isolated LanceDB store (durable data version)."""
    return LanceVectorStore(uri=str(tmp_path / "lancedb"))


class ProcessLocalStore(LanceVectorStore):
    """A real store that reports no durable data version.

    It behaves like a backend that only offers the process-local
    generation counter (for example Chroma), without the optional extra.
    """

    def get_data_version(self, collection_name: str) -> str | None:
        return None


def process_local_store(tmp_path: Path) -> VectorStore:
    """Return a store with only process-local validity."""
    return ProcessLocalStore(uri=str(tmp_path / "lancedb-local"))


def seed(
    store: VectorStore,
    collection: str,
    path: str,
    chunks: int,
    *,
    version: str = "v1",
    profile: str | None = None,
) -> list[str]:
    """Write *chunks* rows for one source with full lineage metadata.

    Returns:
        The chunk ids in index order.
    """
    # The same identity rule ingestion and deletion use.
    source_id = build_source_id(canonical_source_path(path))
    ids, docs, metas, vectors = [], [], [], []
    for index in range(chunks):
        chunk_id = f"chk_{source_id[4:16]}_{version}_{index}"
        ids.append(f"row_{source_id[4:16]}_{version}_{index}")
        docs.append(f"<b>chunk {index}</b> of {path}")
        metas.append(
            {
                "source_id": source_id,
                "source_version": version,
                "chunk_id": chunk_id,
                "source_chunk_index": index,
                "source_chunk_count": chunks,
                "file_path": path,
                "file_name": Path(path).name,
                "page_label": str(index + 1),
            }
        )
        vectors.append([1.0, float(index)])
    store.upsert_precomputed(collection, ids, docs, metas, vectors, embedding_identity=_IDENTITY)
    if profile is not None:
        store.update_collection_metadata(collection, {"profile": profile})
    return [meta["chunk_id"] for meta in metas]


class FakeLLM:
    """Answer LLM double: cites the first supplied source."""

    def __init__(self, text: str = "Chunk zero is first [1].") -> None:
        self.text = text
        self.prompts: list[str] = []

    async def acomplete(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.text)


def make_engine(store: VectorStore, settings: Any, **kwargs: Any) -> Engine:
    """Return a real Engine around *store* with a mock 2-d embedder."""
    return Engine(settings, store=store, embed_model=MockEmbedding(embed_dim=2), **kwargs)


class RecordingEngine(Engine):
    """A real Engine whose search, answer and ingest record their calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[str, tuple, dict]] = []
        self.search_rows: list[dict] = []
        self.answer_result: dict = {}
        self.ingest_result: dict = {"status": "ok"}
        self.raise_on: dict[str, BaseException] = {}

    def search(self, query: str, **kwargs: Any) -> list[dict]:  # type: ignore[override]
        try:
            asyncio.get_running_loop()
            kwargs["_on_event_loop"] = True
        except RuntimeError:
            kwargs["_on_event_loop"] = False
        self.calls.append(("search", (query,), kwargs))
        if "search" in self.raise_on:
            raise self.raise_on["search"]
        return self.search_rows

    async def answer(self, question: str, **kwargs: Any) -> dict:  # type: ignore[override]
        self.calls.append(("answer", (question,), kwargs))
        if "answer" in self.raise_on:
            raise self.raise_on["answer"]
        return self.answer_result

    async def ingest(self, path: str, **kwargs: Any) -> dict:  # type: ignore[override]
        self.calls.append(("ingest", (path,), kwargs))
        if "ingest" in self.raise_on:
            raise self.raise_on["ingest"]
        return self.ingest_result


# ── Application ──────────────────────────────────────────────────────────


def build_app(tmp_path: Path, engine: Any, roots: Iterable[Path] = ()) -> tuple[Any, AccessPolicy]:
    """Create the app around *engine* with a known policy."""
    config = WebConfig(
        workspace=tmp_path / "ws",
        host="127.0.0.1",
        port=8765,
        roots=tuple(roots),
        static_dir=None,
    )
    policy = AccessPolicy.for_launch(config.host, config.port)
    return create_app(config, policy=policy, engine_factory=lambda: engine), policy


def login(client: TestClient, policy: AccessPolicy) -> None:
    """Exchange the bootstrap secret for a session cookie."""
    response = client.post(
        "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
    )
    assert response.status_code == 200, response.text


def bearer(policy: AccessPolicy, *scopes: str) -> dict[str, str]:
    """Return an Authorization header for a new bearer credential."""
    return {"Authorization": f"Bearer {policy.issue_bearer(set(scopes)).token}"}


def wait_for(probe: Callable[[], dict], *, timeout: float = 10.0) -> dict:
    """Poll *probe* until it reports a terminal job status."""
    deadline = time.monotonic() + timeout
    body = probe()
    while body.get("status") not in {"completed", "failed"}:
        if time.monotonic() > deadline:
            raise AssertionError(f"job did not finish: {body}")
        time.sleep(0.02)
        body = probe()
    return body


# ── OpenAPI conformance ──────────────────────────────────────────────────


@lru_cache(maxsize=1)
def openapi_doc() -> dict[str, Any]:
    """Load the reviewed contract once."""
    with OPENAPI.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _deref(node: dict[str, Any]) -> dict[str, Any]:
    doc = openapi_doc()
    while "$ref" in node and node["$ref"].startswith("#/components/responses/"):
        node = doc["components"]["responses"][node["$ref"].rsplit("/", 1)[1]]
    return node


def response_schema(path: str, method: str, status: int) -> dict[str, Any]:
    """Return the declared JSON schema for one operation response.

    An undeclared status code fails: every status the runtime returns
    must be in the contract for that operation.
    """
    doc = openapi_doc()
    responses = doc["paths"][path][method]["responses"]
    declared = responses.get(str(status))
    assert declared is not None, f"{method.upper()} {path} does not declare status {status}"
    schema = _deref(declared)["content"]["application/json"]["schema"]
    return {**copy.deepcopy(schema), "components": doc["components"]}


def assert_conforms(
    path: str, method: str, status: int, body: Any, *, variant: str | None = None
) -> None:
    """Validate *body* against the contract schema for the response.

    Args:
        path: Contract path, relative to the ``/v1`` server URL.
        method: Lower-case HTTP method.
        status: Response status code.
        body: Decoded JSON body.
        variant: For a ``oneOf`` response, the component schema the body
            must match. Plain ``oneOf`` validation also runs, so the body
            must match exactly one branch.
    """
    schema = response_schema(path, method, status)
    jsonschema.Draft202012Validator(schema).validate(body)
    if variant is not None:
        names = [item["$ref"].rsplit("/", 1)[1] for item in schema["oneOf"]]
        assert variant in names, (variant, names)
        schema = {"$ref": f"#/components/schemas/{variant}", "components": schema["components"]}
    jsonschema.Draft202012Validator(schema).validate(body)


def undeclared_keys(schema_name: str, body: dict[str, Any]) -> set[str]:
    """Return top-level keys of *body* that *schema_name* does not declare."""
    declared = openapi_doc()["components"]["schemas"][schema_name].get("properties", {})
    return set(body) - set(declared)
