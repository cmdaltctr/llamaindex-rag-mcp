"""The single install job on the web runtime (task 2.2).

A fake ``uv`` shell script in ``tmp_path`` stands in for the real program.
It records its arguments and environment, prints known lines and exits
with a chosen code. No test reaches the network or installs a package.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from omrs.transports.api.install_job import (  # noqa: E402
    MAX_OUTPUT_LINES,
    InstallJob,
    InstallRunning,
)
from omrs.transports.api.lifespan import WebRuntime  # noqa: E402

PACKAGES = ["llama-index-llms-anthropic>=0.11.0"]
KEY = "sk-test-0123456789abcdefghij"  # gitleaks:allow


def fake_uv(tmp_path: Path, body: str) -> str:
    """Write an executable ``uv`` that records argv and env, then runs *body*."""
    script = tmp_path / "bin" / "uv"
    script.parent.mkdir(parents=True, exist_ok=True)
    out = shlex.quote(str(tmp_path))
    script.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > {out}/argv.txt\nenv > {out}/env.txt\n{body}\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def _job(**kwargs: Any) -> InstallJob:
    return InstallJob(python="/env/bin/python", **kwargs)


async def _run(job: InstallJob, uv: str, **kwargs: Any) -> dict[str, Any]:
    job.start("anthropic", uv, PACKAGES, **kwargs)
    await job.wait()
    return job.snapshot()


def test_the_job_is_a_runtime_field_and_starts_idle() -> None:
    job = WebRuntime.__dataclass_fields__["installs"].default_factory()  # type: ignore[misc]
    assert isinstance(job, InstallJob)
    snapshot = job.snapshot()
    assert snapshot == {
        "state": "idle",
        "extra": None,
        "started_at": None,
        "finished_at": None,
        "reason": None,
        "exit_code": None,
        "output": [],
    }
    assert job.timeout == 600


async def test_success_records_restart_needed(tmp_path: Path) -> None:
    job = _job()
    snapshot = await _run(job, fake_uv(tmp_path, "echo Installed 1 package\nexit 0"))
    assert snapshot["state"] == "succeeded"
    assert snapshot["extra"] == "anthropic"
    assert snapshot["exit_code"] == 0 and snapshot["reason"] is None
    assert snapshot["started_at"] and snapshot["finished_at"]
    assert snapshot["output"] == ["Installed 1 package"]
    assert job.restart_needed == {"anthropic"}


async def test_argv_is_a_fixed_list_into_the_own_python(tmp_path: Path) -> None:
    await _run(_job(), fake_uv(tmp_path, "exit 0"))
    argv = (tmp_path / "argv.txt").read_text(encoding="utf-8").splitlines()
    assert argv == ["pip", "install", "--python", "/env/bin/python", *PACKAGES]


async def test_the_process_gets_no_shell_and_no_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    real = asyncio.create_subprocess_exec

    async def spy(*args: Any, **kwargs: Any) -> Any:
        seen["args"], seen["kwargs"] = args, kwargs
        return await real(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    uv = fake_uv(tmp_path, "exit 0")
    await _run(_job(), uv)
    assert seen["args"][0] == uv
    assert seen["kwargs"]["stdin"] == asyncio.subprocess.DEVNULL
    assert seen["kwargs"]["stderr"] == asyncio.subprocess.STDOUT
    assert "shell" not in seen["kwargs"]


async def test_failure_keeps_the_output_and_no_restart(tmp_path: Path) -> None:
    job = _job()
    body = "echo resolving >&2\necho 'error: no solution' >&2\nexit 2"
    snapshot = await _run(job, fake_uv(tmp_path, body))
    assert snapshot["state"] == "failed"
    assert snapshot["reason"] == "exit-code" and snapshot["exit_code"] == 2
    assert snapshot["output"] == ["resolving", "error: no solution"]
    assert job.restart_needed == set()


async def test_only_the_last_forty_lines_are_kept(tmp_path: Path) -> None:
    body = "i=1\nwhile [ $i -le 55 ]; do echo line $i; i=$((i+1)); done\nexit 0"
    snapshot = await _run(_job(), fake_uv(tmp_path, body))
    assert len(snapshot["output"]) == MAX_OUTPUT_LINES == 40
    assert snapshot["output"][0] == "line 16" and snapshot["output"][-1] == "line 55"


async def test_a_slow_install_times_out_and_is_stopped(tmp_path: Path) -> None:
    job = _job(timeout=0.3)
    snapshot = await _run(job, fake_uv(tmp_path, "echo started\nsleep 30\necho never"))
    assert snapshot["state"] == "failed" and snapshot["reason"] == "timed-out"
    assert snapshot["exit_code"] is None
    assert snapshot["output"] == ["started"]
    assert job.restart_needed == set()


async def test_a_program_that_cannot_start_fails_with_start_failed(tmp_path: Path) -> None:
    snapshot = await _run(_job(), str(tmp_path / "missing-uv"))
    assert snapshot["state"] == "failed" and snapshot["reason"] == "start-failed"
    assert snapshot["output"] == []


async def test_a_second_start_while_running_is_refused(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    body = f"while [ ! -f {shlex.quote(str(gate))} ]; do sleep 0.02; done\nexit 0"
    job = _job()
    job.start("azure", fake_uv(tmp_path, body), ["azure-ai-documentintelligence>=1.0.0"])
    assert job.snapshot()["state"] == "running"
    with pytest.raises(InstallRunning):
        job.start("chroma", "/bin/false", ["chromadb"])
    assert job.snapshot()["extra"] == "azure"
    gate.write_text("", encoding="utf-8")
    await job.wait()
    assert job.snapshot()["state"] == "succeeded"
    assert job.restart_needed == {"azure"}


async def test_api_keys_are_not_passed_and_never_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("anthropic_api_key", "lower-case-secret-value-123")
    monkeypatch.setenv("OMRS_KEEP_ME", "visible")
    body = f"echo token {KEY} here\necho provider-secret-value\nexit 0"
    redactor = lambda text: text.replace("provider-secret-value", "[hidden]")  # noqa: E731
    snapshot = await _run(_job(), fake_uv(tmp_path, body), redactor=redactor)
    env = (tmp_path / "env.txt").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" not in env and "anthropic_api_key=" not in env
    assert KEY not in env and "OMRS_KEEP_ME=visible" in env
    text = "\n".join(snapshot["output"])
    assert KEY not in text and "***" in text
    assert "provider-secret-value" not in text and "[hidden]" in text
