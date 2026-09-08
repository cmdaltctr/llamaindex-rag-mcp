"""Offline contracts for experiment 25 EMBED and adapter request accounting."""

from __future__ import annotations

import asyncio
import json
import runpy
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import lancedb
import pytest
from llama_index.core.schema import MetadataMode, TextNode
from llama_index.embeddings.openai_like import OpenAILikeEmbedding

from omrg.integrations import tokenizer as tokenizer_module

EXP_DIR = Path(__file__).resolve().parents[1] / "experiments/25-token-chunking-ablation-2026-09-08"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if any test attempts a network connection."""

    def refuse(*args: object, **kwargs: object) -> None:
        pytest.fail("Network access is forbidden in offline accounting tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_installed_adapter_normalises_request_text(
    monkeypatch: pytest.MonkeyPatch, asynchronous: bool
) -> None:
    """Exercise inherited OpenAI batch helpers through the installed adapter."""
    texts = ["title: A\n\nbody\nend", "unchanged\ttext\r\nnext"]
    response = SimpleNamespace(data=[SimpleNamespace(embedding=[1.0]) for _ in texts])
    create = AsyncMock(return_value=response) if asynchronous else Mock(return_value=response)
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    monkeypatch.setattr(OpenAILikeEmbedding, "_get_client", lambda self: client)
    monkeypatch.setattr(OpenAILikeEmbedding, "_get_aclient", lambda self: client)
    adapter = OpenAILikeEmbedding(model_name="offline-test", api_key="fake")

    if asynchronous:
        result = asyncio.run(adapter.aget_text_embedding_batch(texts))
        create.assert_awaited_once()
    else:
        result = adapter.get_text_embedding_batch(texts)
        create.assert_called_once()

    assert result == [[1.0], [1.0]]
    assert create.call_args.kwargs["input"] == ["title: A  body end", "unchanged\ttext\r next"]
    assert texts == ["title: A\n\nbody\nend", "unchanged\ttext\r\nnext"]


@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_verifier_counts_embed_and_normalised_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, side: str
) -> None:
    """Count real serialised nodes, retaining both totals and both maxima."""
    nodes = [
        TextNode(
            text="body\nend",
            metadata={"file_path": "/corpus/a.md", "title": "A", "secret": "excluded"},
            excluded_embed_metadata_keys=["file_path", "secret"],
        ),
        TextNode(
            text="short\r\n\ttail",
            metadata={"file_path": "/corpus/b.md"},
            excluded_embed_metadata_keys=["file_path"],
        ),
    ]
    rows = [
        {
            "text": "wrong row text",
            "metadata": {
                "_node_content": node.to_json(),
                "content_type": None,
            },
        }
        for node in nodes
    ]
    arrow = SimpleNamespace(to_pylist=lambda: rows)
    table = SimpleNamespace(to_arrow=lambda: arrow)
    monkeypatch.setattr(
        lancedb, "connect", lambda uri: SimpleNamespace(open_table=lambda name: table)
    )
    encoded: list[str] = []

    def encode(text: str, *, add_special_tokens: bool) -> SimpleNamespace:
        assert add_special_tokens is False
        encoded.append(text)
        # Deliberately distinguish newline and space costs without a downloaded model.
        return SimpleNamespace(ids=[0] * (len(text) + text.count("\n")))

    monkeypatch.setattr(
        tokenizer_module, "load_tokenizer", lambda *args: SimpleNamespace(encode=encode)
    )
    build = tmp_path / "build.json"
    build.write_text(
        json.dumps(
            {
                "packs": {
                    "test": {
                        "file_details": [
                            {"file": "a.md", "status": "indexed", "chunks": 1},
                            {"file": "b.md", "status": "indexed", "chunks": 1},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["verify_accounting.py", "--side", side])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    namespace = runpy.run_path(str(EXP_DIR / "verify_accounting.py"))
    namespace["main"].__globals__.update(
        EXP_DIR=tmp_path, SIDES={side: {"uri": tmp_path, "table": "test", "build": build}}
    )
    namespace["main"]()
    report = json.loads((tmp_path / f"output/verify_accounting_{side}.json").read_text())

    payloads = [node.get_content(metadata_mode=MetadataMode.EMBED) for node in nodes]
    requests = [payload.replace("\n", " ") for payload in payloads]
    payload_counts = [len(text) + text.count("\n") for text in payloads]
    request_counts = [len(text) for text in requests]
    assert report["payload_tokens"] == sum(payload_counts)
    assert report["max_payload_tokens"] == max(payload_counts)
    assert report["request_tokens"] == sum(request_counts)
    assert report["max_request_tokens"] == max(request_counts)
    assert sorted(encoded) == sorted(payloads + requests)
    assert report["payload_tokens"] > report["request_tokens"]
    assert report["chunks"] == report["files"] == report["recorded_files"] == 2
    assert report["mismatch_count"] == 0


def test_paid_build_still_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """The forced build must exit before runtime setup or ingestion imports."""
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--force"])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    # Isolate the legacy runner's process-local environment changes.
    import os

    monkeypatch.setattr(os, "environ", os.environ.copy())
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(EXP_DIR / "build_index.py"), run_name="__main__")
    assert exc.value.code == 1
