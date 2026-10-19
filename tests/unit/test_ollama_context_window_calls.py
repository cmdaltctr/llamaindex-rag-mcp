"""The Ollama context window reaches every Ollama call (Parts A.2 and A.3, TDR-036).

A fake HTTP server stands in for Ollama and records each request. No real
Ollama is started or contacted.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from llama_index.core.llms import ChatMessage
from tests.test_metadata_extractor import _GOOD_RESPONSE, _capturing_async_client, _set_mode

from omrg.config import Settings
from omrg.core.providers.llm import ollama

#: Model maximum that the fake ``/api/show`` would report if it were asked.
MODEL_MAXIMUM = 262144


class FakeOllama:
    """A recording fake of the Ollama chat and show routes."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return

            def do_POST(self) -> None:
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size) or b"{}")
                owner.requests.append((self.path, body))
                if self.path == "/api/show":
                    reply: dict[str, Any] = {"model_info": {"qwen3.context_length": MODEL_MAXIMUM}}
                else:
                    reply = {
                        "model": "m",
                        "created_at": "2026-10-18T00:00:00Z",
                        "message": {"role": "assistant", "content": "hello"},
                        "done": True,
                        "done_reason": "stop",
                    }
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def paths(self) -> list[str]:
        return [path for path, _ in self.requests]


@pytest.fixture
def fake() -> Iterator[FakeOllama]:
    server = FakeOllama()
    thread = threading.Thread(target=server.server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.server.shutdown()
    server.server.server_close()
    thread.join(timeout=5)


def chat(fake: FakeOllama, **settings: Any) -> None:
    config = Settings(_env_file=None, ollama_base_url=fake.url, **settings)
    llm = ollama.build(config, answer_model="qwen3:4b")
    llm.chat([ChatMessage(role="user", content="hi")])


def test_chat_sends_the_default_window_and_never_asks_for_the_model_maximum(
    fake: FakeOllama,
) -> None:
    chat(fake)
    assert fake.paths() == ["/api/chat"]
    assert fake.requests[0][1]["options"]["num_ctx"] == 16384


def test_chat_sends_the_configured_window(fake: FakeOllama) -> None:
    chat(fake, ollama_context_window=8192)
    assert "/api/show" not in fake.paths()
    assert fake.requests[0][1]["options"]["num_ctx"] == 8192


# ── Metadata extraction ──────────────────────────────────────────────────


def test_metadata_generate_carries_num_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.core.metadata import extract_metadata_async

    _set_mode(
        monkeypatch, "local", local_backend="ollama", max_attempts=1, ollama_context_window=8192
    )
    payloads = _capturing_async_client(monkeypatch, [_GOOD_RESPONSE])
    asyncio.run(extract_metadata_async("transformer attention"))
    assert payloads[0]["options"] == {"num_ctx": 8192}
    assert payloads[0]["format"] == "json"


def test_metadata_generate_uses_the_default_window(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.core.metadata import extract_metadata_async

    _set_mode(monkeypatch, "local", local_backend="ollama", max_attempts=1)
    payloads = _capturing_async_client(monkeypatch, [_GOOD_RESPONSE])
    asyncio.run(extract_metadata_async("transformer attention"))
    assert payloads[0]["options"]["num_ctx"] == 16384
