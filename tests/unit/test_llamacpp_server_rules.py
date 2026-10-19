"""Launch rules of the managed llama.cpp server: program, model, port, argv, environment.

Pure checks, no process starts. Files are temporary; the programs are small
stand-ins and nothing here runs a real ``llama-server``.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from omrg.core.providers.llm import llamacpp_rules as rules

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes and links")
HF_TOKEN = "hf_FAKE_TOKEN_FOR_TESTS"  # noqa: S105  # gitleaks:allow
FAKE_KEY = "sk-or-v1-FAKEKEYFORTESTS0123456789"  # gitleaks:allow


def make_program(folder: Path, name: str = "llama-server", mode: int = 0o755) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(mode)
    return path


# ── Program ──────────────────────────────────────────────────────────────


@POSIX
def test_a_regular_executable_named_llama_server_is_accepted(tmp_path: Path) -> None:
    assert rules.check_binary(str(make_program(tmp_path / "bin")))


@POSIX
def test_a_package_manager_link_to_llama_server_is_accepted(tmp_path: Path) -> None:
    real = make_program(tmp_path / "cellar")
    link = tmp_path / "bin" / "llama-server"
    link.parent.mkdir()
    link.symlink_to(real)
    assert rules.check_binary(str(link))


@POSIX
def test_a_link_named_llama_server_that_points_at_a_shell_is_refused(tmp_path: Path) -> None:
    link = tmp_path / "llama-server"
    link.symlink_to("/bin/sh")
    assert not rules.check_binary(str(link))


@POSIX
def test_a_link_with_another_name_to_the_right_file_is_refused(tmp_path: Path) -> None:
    real = make_program(tmp_path / "cellar")
    link = tmp_path / "server"
    link.symlink_to(real)
    assert not rules.check_binary(str(link))


@POSIX
@pytest.mark.parametrize("name", ["llama-server-old", "llama-server.exe", "Llama-Server", "sh"])
def test_another_file_name_is_refused(tmp_path: Path, name: str) -> None:
    assert not rules.check_binary(str(make_program(tmp_path, name)))


@POSIX
@pytest.mark.parametrize("value", ["llama-server", "./bin/llama-server", "bin/llama-server", ""])
def test_a_relative_or_empty_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    make_program(tmp_path / "bin")
    make_program(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert not rules.check_binary(value)


@POSIX
def test_a_directory_named_llama_server_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "llama-server"
    folder.mkdir()
    assert not rules.check_binary(str(folder))


@POSIX
def test_a_file_that_cannot_be_run_is_refused(tmp_path: Path) -> None:
    assert not rules.check_binary(str(make_program(tmp_path, mode=0o644)))


@POSIX
def test_a_missing_file_and_a_trailing_slash_are_refused(tmp_path: Path) -> None:
    program = make_program(tmp_path)
    assert not rules.check_binary(str(tmp_path / "absent" / "llama-server"))
    assert not rules.check_binary(f"{program}/")


@POSIX
def test_the_file_is_checked_again_after_it_changes(tmp_path: Path) -> None:
    program = make_program(tmp_path)
    assert rules.check_binary(str(program))
    program.unlink()
    program.mkdir()
    assert not rules.check_binary(str(program))


def test_a_nul_byte_is_refused() -> None:
    assert not rules.check_binary("/opt/llama/llama-server\x00")


def test_the_windows_name_is_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "IS_WINDOWS", True)
    assert rules.binary_names() == frozenset({"llama-server.exe"})
    monkeypatch.setattr(rules, "IS_WINDOWS", False)
    assert rules.binary_names() == frozenset({"llama-server"})


# ── Model ────────────────────────────────────────────────────────────────


def test_an_existing_gguf_file_is_a_file_model(tmp_path: Path) -> None:
    model = tmp_path / "Qwen3-4B-Q8_0.GGUF"
    model.write_bytes(b"GGUF")
    assert rules.model_kind(str(model)) == "file"


def test_a_path_with_a_space_or_a_semicolon_is_still_one_model(tmp_path: Path) -> None:
    model = tmp_path / "my models; rm -rf" / "q.gguf"
    model.parent.mkdir()
    model.write_bytes(b"GGUF")
    assert rules.model_kind(str(model)) == "file"


@pytest.mark.parametrize("value", ["Qwen/Qwen3-0.6B-GGUF", "Qwen/Qwen3-0.6B-GGUF:Q8_0", "a/b"])
def test_a_hugging_face_id_is_accepted(value: str) -> None:
    assert rules.model_kind(value) == "hf"


@pytest.mark.parametrize(
    "value",
    [
        "--api-key",
        "-m",
        "-hf",
        "a b",
        "org/",
        "/name",
        "../x",
        "org/name:",
        "org/name:ta g",
        "org/name\n",
        "org/na;me",
        "org/name:tag:more",
        "org/na$(id)",
        "org//name",
        "a/b/c",
        "-org/name",
        "",
        "   ",
        "x" * 97 + "/y",
    ],
)
def test_a_malformed_model_is_refused(value: str) -> None:
    assert rules.model_kind(value) is None


def test_a_missing_or_wrong_extension_file_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "model.bin"
    other.write_bytes(b"x")
    assert rules.model_kind(str(other)) is None
    assert rules.model_kind(str(tmp_path / "absent.gguf")) is None


def test_a_directory_named_like_a_gguf_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "dir.gguf"
    folder.mkdir()
    assert rules.model_kind(str(folder)) is None


# ── Port ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "port"),
    [
        ("http://127.0.0.1:8081/v1", 8081),
        ("http://localhost:9000/v1", 9000),
        ("http://[::1]:7000/v1", 7000),
        ("http://LOCALHOST:8081", 8081),
    ],
)
def test_loopback_urls_give_the_port(url: str, port: int) -> None:
    assert rules.chat_port(url) == port


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.20:8081/v1",
        "http://example.com:8081/v1",
        "https://127.0.0.1:8081/v1",
        "http://0.0.0.0:8081/v1",
        "http://127.0.0.1.evil.test:8081/v1",
        "http://user@127.0.0.1:8081/v1",
        "file:///x",
        "",
        "not a url",
        "http://127.0.0.1:99999/v1",
    ],
)
def test_other_urls_are_not_loopback(url: str) -> None:
    assert rules.chat_port(url) is None


# ── Argument list ────────────────────────────────────────────────────────


def test_argv_for_a_file_model_is_exact() -> None:
    argv = rules.build_argv("/opt/llama/llama-server", "/m/q.gguf", "file", 8081, 16384)
    assert argv == [
        "/opt/llama/llama-server",
        "-m",
        "/m/q.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "8081",
        "-c",
        "16384",
    ]


def test_argv_for_a_hugging_face_model_uses_hf() -> None:
    argv = rules.build_argv("/b/llama-server", "Qwen/Qwen3-0.6B-GGUF:Q8_0", "hf", 9000, 4096)
    assert argv[:3] == ["/b/llama-server", "-hf", "Qwen/Qwen3-0.6B-GGUF:Q8_0"]
    assert argv[3:] == ["--host", "127.0.0.1", "--port", "9000", "-c", "4096"]


def test_argv_has_no_other_flag() -> None:
    argv = rules.build_argv("/b/llama-server", "/m/q.gguf", "file", 8081, 2048)
    flags = [item for item in argv if item.startswith("-")]
    assert flags == ["-m", "--host", "--port", "-c"]


# ── Environment ──────────────────────────────────────────────────────────

FULL = {
    "PATH": "/usr/bin",
    "HOME": "/home/u",
    "LANG": "en_GB.UTF-8",
    "TMPDIR": "/tmp",
    "LLAMA_CACHE": "/cache",
    "HF_HOME": "/hf",
    "HF_TOKEN": HF_TOKEN,
    "OPENROUTER_API_KEY": FAKE_KEY,
    "OPENAI_API_KEY": FAKE_KEY,
    "ANTHROPIC_API_KEY": FAKE_KEY,
    "OPENAI_COMPATIBLE_API_KEY": FAKE_KEY,
    "AWS_SECRET_ACCESS_KEY": FAKE_KEY,
    "PYTHONPATH": "/evil",
    "LD_PRELOAD": "/evil.so",
    "DYLD_INSERT_LIBRARIES": "/evil.dylib",
}


def test_a_file_model_gets_only_the_four_base_variables() -> None:
    assert rules.child_environment(FULL, "file") == {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LANG": "en_GB.UTF-8",
        "TMPDIR": "/tmp",
    }


def test_a_hugging_face_model_also_gets_the_cache_and_token_variables_that_are_set() -> None:
    env = rules.child_environment(FULL, "hf")
    assert set(env) == {"PATH", "HOME", "LANG", "TMPDIR", "LLAMA_CACHE", "HF_HOME", "HF_TOKEN"}
    assert env["HF_TOKEN"] == HF_TOKEN


def test_a_hugging_face_variable_that_is_not_set_is_not_invented() -> None:
    assert "HF_TOKEN" not in rules.child_environment({"PATH": "/usr/bin"}, "hf")


def test_no_provider_key_ever_reaches_the_child() -> None:
    for kind in ("file", "hf"):
        env = rules.child_environment(FULL, kind)
        assert not any(FAKE_KEY in value for value in env.values())
        assert not {"OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"} & set(env)


def test_the_real_environment_function_reads_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    assert "OPENROUTER_API_KEY" not in rules.child_environment(os.environ, "hf")


def test_make_program_helper_is_executable(tmp_path: Path) -> None:
    program = make_program(tmp_path)
    assert program.stat().st_mode & stat.S_IXUSR


# ── Idle sleep (task 17.9) ───────────────────────────────────────────────


def test_argv_adds_the_idle_sleep_flag_when_above_zero() -> None:
    argv = rules.build_argv("/b/llama-server", "/m/q.gguf", "file", 8081, 16384, idle_sleep=300)
    assert argv[-4:] == ["--sleep-idle-seconds", "300", "-c", "16384"]
    assert [item for item in argv if item.startswith("-")] == [
        "-m",
        "--host",
        "--port",
        "--sleep-idle-seconds",
        "-c",
    ]


def test_argv_has_no_idle_sleep_flag_at_zero() -> None:
    argv = rules.build_argv("/b/llama-server", "/m/q.gguf", "file", 8081, 16384, idle_sleep=0)
    assert "--sleep-idle-seconds" not in argv


def test_the_idle_sleep_field_is_a_whole_number_from_zero_to_a_day() -> None:
    field = next(f for f in rules.LLAMACPP_SERVER_FIELDS if f.id == "idle_sleep")
    assert (field.kind, field.settings_field, field.env_var) == (
        "int",
        "llamacpp_idle_sleep_seconds",
        "LLAMACPP_IDLE_SLEEP_SECONDS",
    )
    assert (field.minimum, field.maximum) == (0, 86400)
