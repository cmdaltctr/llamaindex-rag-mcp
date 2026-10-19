"""The web server keeps its settings in ``omrg.jsonc`` (ADR-087, tasks 5.1, 5.3, 5.5, 5.6).

The routes write the file and read it back, a hand edit applies at the next
request, a key lives only in the keychain behind a ``keychain://`` reference,
and no refused value appears in an answer. The keychain is a fake and the user
config folder is a temporary one (``OMRG_CONFIG_DIR``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402

from omrg.config.settings_file import read_settings_file  # noqa: E402
from omrg.config.settings_file_write import write_settings  # noqa: E402
from omrg.config.user_config import user_config_dir  # noqa: E402

harness = edit.harness
KEY = edit.KEY64
OTHER_KEY = "sk-or-v1-" + "Q9w8E7r6T5y4U3i2" * 3 + "Aa1Bb2C"  # fake, 64 characters
STALE = "omrg.jsonc changed on disk. Reload to see the new values."


def hand_edit(changes: dict[str, Any]) -> None:
    """Change the file as a text editor would: no revision, outside the server."""
    write_settings(changes, revision=None)


# ── Live reload by file stamp (task 5.5) ─────────────────────────────────


def test_a_hand_edit_of_the_chat_model_applies_at_the_next_request(harness: Any) -> None:
    with harness() as h:
        assert h.engines[0]._effective_settings.answer.model == "answer-model"
        hand_edit({"answer.provider": "llamacpp", "answer.model": "edited-by-hand"})
        chat = h.client.get("/v1/settings/chat").json()
        assert (chat["provider"], chat["model"], chat["source"]) == (
            "llamacpp",
            "edited-by-hand",
            "config-file",
        )
        assert h.engines[0]._effective_settings.answer.model == "edited-by-hand"
        assert chat["revision"] == read_settings_file().revision


def test_removing_a_key_by_hand_returns_the_value_to_its_default(harness: Any) -> None:
    with harness() as h:
        hand_edit({"ollama_base_url": edit.NEW_URL})
        assert h.field("ollama", "base_url")["value"] == edit.NEW_URL
        assert edit.answer_url(h) == edit.NEW_URL
        hand_edit({"ollama_base_url": None})
        field = h.field("ollama", "base_url")
        assert (field["value"], field["source"]) == ("http://ollama.test:11434", "default")
        assert edit.answer_url(h) is None


def test_a_hand_edit_of_an_engine_setting_is_not_applied_live(harness: Any) -> None:
    with harness() as h:
        before = h.engines[0]._effective_settings.retrieval.top_k
        hand_edit({"ollama_base_url": edit.NEW_URL})  # one live key, so a reload happens
        (user_config_dir() / "omrg.jsonc").write_text(
            f'{{ "retrieval": {{ "top_k": 3 }}, "ollama_base_url": "{edit.NEW_URL}" }}'
        )
        h.client.get("/v1/settings/chat")
        assert edit.answer_url(h) == edit.NEW_URL
        assert h.engines[0]._effective_settings.retrieval.top_k == before != 3


def test_a_broken_file_gives_the_defaults_and_the_server_stays_up(harness: Any) -> None:
    with harness() as h:
        hand_edit({"ollama_base_url": edit.NEW_URL})
        (user_config_dir() / "omrg.jsonc").write_text("{ not json", encoding="utf-8")
        assert h.field("ollama", "base_url")["source"] == "default"
        assert h.client.get("/v1/connections").status_code == 200


def test_an_unchanged_file_is_not_read_again(harness: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    with harness() as h:
        state = h.app.state.runtime.providers
        reads: list[int] = []
        real = state.store.read
        monkeypatch.setattr(state.store, "read", lambda: reads.append(1) or real())
        h.client.get("/v1/connections")
        h.client.get("/v1/settings/chat")
        assert reads == []  # the stamp did not change
        hand_edit({"ollama_base_url": edit.NEW_URL})
        h.client.get("/v1/connections")
        assert len(reads) >= 1


def test_a_page_save_does_not_rebuild_the_engine_a_second_time(harness: Any) -> None:
    with harness() as h:
        calls: list[Any] = []
        engine = h.engines[0]
        real = engine.use_provider_settings
        engine.use_provider_settings = lambda e: (calls.append(e), real(e))[1]
        assert h.put("ollama", {"base_url": edit.NEW_URL}).status_code == 200
        h.client.get("/v1/connections")  # the stamp changed by our own write
        assert len(calls) == 1


# ── Revisions (task 5.1) ─────────────────────────────────────────────────


def test_every_settings_read_returns_a_revision(harness: Any) -> None:
    with harness() as h:
        for path in (
            "/v1/connections",
            "/v1/settings/chat",
            "/v1/mcp",
            "/v1/llamacpp/server",
            "/v1/settings/web-port",
            "/v1/settings/upload-limit",
        ):
            body = h.client.get(path).json()
            assert isinstance(body["revision"], str) and body["revision"], path


def test_a_stale_revision_is_409_with_the_reload_message_on_every_save(harness: Any) -> None:
    with harness() as h:
        first = h.client.get("/v1/connections").json()["revision"]
        hand_edit({"web_port": 9100})
        key_ref = '"openrouter_api_key"'
        attempts = [
            h.client.put(
                "/v1/connections/ollama",
                json={"fields": {"base_url": edit.NEW_URL}, "revision": first},
                headers=edit.ORIGIN,
            ),
            h.client.put(
                "/v1/connections/openrouter/key",
                json={"api_key": KEY, "revision": first},
                headers=edit.ORIGIN,
            ),
            h.client.request(
                "DELETE",
                "/v1/connections/openrouter/key",
                json={"revision": first},
                headers=edit.ORIGIN,
            ),
            h.client.put(
                "/v1/settings/chat",
                json={"provider": "ollama", "model": "m", "revision": first},
                headers=edit.ORIGIN,
            ),
            h.client.put("/v1/settings/chat", json={"revision": first}, headers=edit.ORIGIN),
        ]
        for response in attempts:
            assert response.status_code == 409, response.text
            assert response.json()["message"] == STALE
        assert h.keychain.data == {}
        assert key_ref not in h.file_text() and edit.NEW_URL not in h.file_text()
        assert '"web_port": 9100' in h.file_text()  # the hand edit stayed


def test_a_save_returns_the_revision_the_next_read_returns(harness: Any) -> None:
    with harness() as h:
        saved = h.put("ollama", {"base_url": edit.NEW_URL}).json()["revision"]
        assert saved == h.client.get("/v1/connections").json()["revision"]
        assert saved == read_settings_file().revision
        chat = h.client.put(
            "/v1/settings/chat",
            json={"provider": "llamacpp", "model": "m", "revision": saved},
            headers=edit.ORIGIN,
        )
        assert chat.status_code == 200 and chat.json()["revision"] != saved


def test_a_save_with_the_current_revision_succeeds(harness: Any) -> None:
    with harness() as h:
        revision = h.client.get("/v1/connections").json()["revision"]
        assert h.put("ollama", {"base_url": edit.NEW_URL}, revision=revision).status_code == 200


def test_a_broken_file_is_not_overwritten_by_a_save(harness: Any) -> None:
    with harness() as h:
        user_config_dir().mkdir(parents=True, exist_ok=True)
        (user_config_dir() / "omrg.jsonc").write_text("{ not json", encoding="utf-8")
        response = h.put("ollama", {"base_url": edit.NEW_URL})
        assert response.status_code == 409
        assert response.json()["message"] == (
            "omrg.jsonc could not be read. Fix it, then save again."
        )
        assert (user_config_dir() / "omrg.jsonc").read_text() == "{ not json"


def test_a_save_keeps_comments_and_other_keys(harness: Any) -> None:
    with harness() as h:
        user_config_dir().mkdir(parents=True, exist_ok=True)
        (user_config_dir() / "omrg.jsonc").write_text(
            '// my notes\n{\n  "retrieval": { "top_k": 7 }, // keep\n  "web_port": 9100\n}\n',
            encoding="utf-8",
        )
        assert h.put("ollama", {"base_url": edit.NEW_URL}).status_code == 200
        text = h.file_text()
        assert "// my notes" in text and "// keep" in text
        assert '"top_k": 7' in text and '"web_port": 9100' in text
        assert edit.NEW_URL in text


# ── An address from the file edits and is written back (spec: no 409) ────


def test_a_jsonc_address_is_editable_over_http(harness: Any) -> None:
    with harness() as h:
        hand_edit({"ollama_base_url": "http://from-file:1"})
        field = h.field("ollama", "base_url")
        assert (field["source"], field["locked"], field["value"]) == (
            "config-file",
            False,
            "http://from-file:1",
        )
        assert h.put("ollama", {"base_url": edit.NEW_URL}).status_code == 200
        assert f'"ollama_base_url": "{edit.NEW_URL}"' in h.file_text()
        assert "from-file" not in h.file_text()


def test_chat_settings_report_the_config_file_source(harness: Any) -> None:
    with harness() as h:
        hand_edit({"answer.model": "from-file-model"})
        chat = h.client.get("/v1/settings/chat").json()
        assert (chat["model"], chat["source"], chat["locked"]) == (
            "from-file-model",
            "config-file",
            False,
        )
        assert (
            h.client.put(
                "/v1/settings/chat",
                json={"provider": "llamacpp", "model": "page-model"},
                headers=edit.ORIGIN,
            ).status_code
            == 200
        )


def test_a_dotenv_value_locks_and_reports_dotenv(harness: Any) -> None:
    sources = {"llamacpp_chat_url": "dotenv"}
    with harness(explicit=frozenset({"llamacpp_chat_url"}), sources=sources) as h:
        field = h.field("llamacpp", "chat_url")
        assert (field["source"], field["locked"]) == ("dotenv", True)
        response = h.put("llamacpp", {"chat_url": "http://other:8081/v1"})
        assert response.status_code == 409
        assert "LLAMACPP_CHAT_URL" in response.json()["message"]
        assert h.file_text() == ""


# ── Keys live only in the keychain, referenced from the file (task 5.3) ──


def put_key(h: Any, key: str = KEY, **extra: Any) -> Any:
    return h.client.put(
        "/v1/connections/openrouter/key", json={"api_key": key, **extra}, headers=edit.ORIGIN
    )


def delete_key(h: Any) -> Any:
    return h.client.delete("/v1/connections/openrouter/key", headers=edit.ORIGIN)


def files_under(*roots: Path) -> list[Path]:
    return [p for root in roots if root.exists() for p in root.rglob("*") if p.is_file()]


def test_a_saved_key_is_in_the_keychain_and_in_no_file(harness: Any, tmp_path: Path) -> None:
    with harness() as h:
        assert put_key(h).status_code == 200
        assert h.keychain.data == {"openrouter": KEY}
        assert '"openrouter_api_key": "keychain://openrouter"' in h.file_text()
        for path in files_under(user_config_dir(), tmp_path / "ws", Path.cwd() / ".env"):
            assert KEY.encode() not in path.read_bytes(), path
        field = h.field("openrouter", "api_key")
        assert (field["set"], field["source"], field["locked"]) == (True, "keychain", False)


def test_a_page_key_replaces_a_file_reference_and_leaves_the_key_file(harness: Any) -> None:
    secrets = user_config_dir() / "secrets"
    secrets.mkdir(parents=True, mode=0o700)
    key_file = secrets / "openrouter.key"
    key_file.write_text(OTHER_KEY, encoding="utf-8")
    key_file.chmod(0o600)
    hand_edit({"openrouter_api_key": f"file://{key_file}"})
    with harness() as h:
        field = h.field("openrouter", "api_key")
        assert (field["source"], field["locked"]) == ("key-file", False)
        assert put_key(h).status_code == 200
        assert '"openrouter_api_key": "keychain://openrouter"' in h.file_text()
        assert str(key_file) not in h.file_text()
        assert key_file.read_text(encoding="utf-8") == OTHER_KEY
        assert h.field("openrouter", "api_key")["source"] == "keychain"


def test_the_page_key_beats_an_implicit_key_file_and_removal_falls_back(harness: Any) -> None:
    secrets = user_config_dir() / "secrets"
    secrets.mkdir(parents=True, mode=0o700)
    (secrets / "openrouter.key").write_text(OTHER_KEY, encoding="utf-8")
    (secrets / "openrouter.key").chmod(0o600)
    with harness() as h:
        assert h.field("openrouter", "api_key")["source"] == "key-file"
        assert put_key(h).status_code == 200
        assert h.field("openrouter", "api_key")["source"] == "keychain"
        assert h.app.state.runtime.providers.values.values["openrouter_api_key"] == KEY
        assert delete_key(h).status_code == 200
        field = h.field("openrouter", "api_key")
        assert (field["source"], field["set"]) == ("key-file", True)
        assert (secrets / "openrouter.key").read_text(encoding="utf-8") == OTHER_KEY
        assert h.keychain.data == {}


def test_an_env_reference_does_not_lock_the_key_field(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MY_ROUTER_KEY", OTHER_KEY)
    hand_edit({"openrouter_api_key": "env://MY_ROUTER_KEY"})
    with harness() as h:
        field = h.field("openrouter", "api_key")
        assert (field["source"], field["locked"], field["set"]) == ("config-file", False, True)
        assert put_key(h).status_code == 200
        assert '"openrouter_api_key": "keychain://openrouter"' in h.file_text()
        assert "env://MY_ROUTER_KEY" not in h.file_text()


def test_removing_a_key_deletes_the_entry_and_the_reference_only(harness: Any) -> None:
    with harness() as h:
        hand_edit({"web_port": 9100})
        put_key(h)
        response = delete_key(h)
        assert response.status_code == 200
        assert response.json()["revision"] == read_settings_file().revision
        assert h.keychain.data == {}
        assert "openrouter_api_key" not in h.file_text()
        assert '"web_port": 9100' in h.file_text()
        field = h.field("openrouter", "api_key")
        assert (field["source"], field["set"]) == ("none", False)


def test_removing_leaves_an_env_reference_in_place(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MY_ROUTER_KEY", OTHER_KEY)
    hand_edit({"openrouter_api_key": "env://MY_ROUTER_KEY"})
    with harness() as h:
        assert delete_key(h).status_code == 200
        assert '"openrouter_api_key": "env://MY_ROUTER_KEY"' in h.file_text()


def test_a_dotenv_key_locks_the_key_field(harness: Any) -> None:
    sources = {"openrouter_api_key": "dotenv"}
    with harness(
        explicit=frozenset({"openrouter_api_key"}), openrouter_api_key=edit.SECRET, sources=sources
    ) as h:
        field = h.field("openrouter", "api_key")
        assert (field["source"], field["locked"]) == ("dotenv", True)
        assert put_key(h).status_code == 409
        assert delete_key(h).status_code == 409
        assert h.keychain.data == {} and h.file_text() == ""


def test_a_key_reference_without_an_entry_reports_missing_and_no_key(harness: Any) -> None:
    hand_edit({"openrouter_api_key": "keychain://openrouter"})
    with harness() as h:
        field = h.field("openrouter", "api_key")
        assert (field["set"], field["state"]) == (False, "keychain-missing")


def test_a_key_in_the_keychain_without_a_reference_is_not_used(harness: Any) -> None:
    with harness() as h:
        h.keychain.data["openrouter"] = KEY
        assert h.field("openrouter", "api_key")["set"] is False


def test_a_literal_key_in_the_file_is_ignored(harness: Any) -> None:
    (user_config_dir() / "omrg.jsonc").parent.mkdir(parents=True, exist_ok=True)
    (user_config_dir() / "omrg.jsonc").write_text(
        '{ "openrouter_api_key": "sk-or-literal-in-file-0001" }', encoding="utf-8"
    )
    with harness() as h:
        assert h.field("openrouter", "api_key")["set"] is False
        assert "sk-or-literal" not in json.dumps(h.connections())


# ── No refused value in any answer (task 5.6) ────────────────────────────

MARKER = "ZZ-refused-marker-91"
BAD_REQUESTS = [
    ("PUT", "/v1/connections/ollama", {"fields": {"base_url": f"ftp://{MARKER}"}}, 400),
    ("PUT", "/v1/connections/ollama", {"fields": {"context_window": f"{MARKER}"}}, 400),
    ("PUT", "/v1/connections/openrouter/key", {"api_key": f"has space {MARKER}"}, 400),
    ("PUT", "/v1/settings/chat", {"provider": MARKER, "model": "m"}, 400),
    ("PUT", "/v1/settings/chat", {"provider": "ollama", "model": f"{MARKER}\nbad"}, 400),
    ("PUT", "/v1/llamacpp/server", {"binary": f"/no/such/{MARKER}/llama-server"}, 400),
    ("PUT", "/v1/llamacpp/server", {"model": f"--{MARKER}"}, 400),
    ("PUT", "/v1/llamacpp/server", {"context_window": MARKER}, 400),
    ("PUT", "/v1/llamacpp/server", {"idle_sleep": MARKER}, 400),
    ("PUT", "/v1/mcp", {"enabled": MARKER}, 400),
    ("PUT", "/v1/settings/web-port", {"port": 70000}, 400),
    ("PUT", "/v1/settings/web-port", {"port": MARKER}, 400),
    ("PUT", "/v1/settings/upload-limit", {"max_mib": 4096}, 400),
    ("PUT", "/v1/settings/upload-limit", {"max_mib": MARKER}, 400),
]


@pytest.mark.parametrize(("method", "path", "body", "status"), BAD_REQUESTS)
def test_a_refused_save_names_the_rule_and_never_the_value(
    harness: Any, method: str, path: str, body: dict[str, Any], status: int
) -> None:
    with harness() as h:
        response = h.client.request(method, path, json=body, headers=edit.ORIGIN)
        assert response.status_code == status, response.text
        text = response.text
        assert MARKER not in text.replace(f'"{MARKER}"', "")  # a key name may repeat a field
        assert "4096" not in text.replace("1 to 2048", "") and "70000" not in text
        message = response.json()["message"]
        assert message and message.strip()
        assert h.file_text() == ""


def test_a_refused_conflict_names_the_source_and_never_a_value(harness: Any) -> None:
    sources = {"llamacpp_chat_url": "env"}
    with harness(explicit=frozenset({"llamacpp_chat_url"}), sources=sources) as h:
        response = h.put("llamacpp", {"chat_url": f"http://{MARKER}:1/v1"})
        assert response.status_code == 409
        assert MARKER not in response.text
        assert "LLAMACPP_CHAT_URL" in response.json()["message"]
        stale = h.put("llamacpp", {"chat_url": f"http://{MARKER}:1/v1"}, revision="deadbeef")
        assert stale.status_code == 409 and MARKER not in stale.text
