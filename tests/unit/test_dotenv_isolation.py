"""A developer's ``.env`` or shell keys must not reach a test.

A ``.env`` in the working folder reaches a test two ways: ``omrg.config`` copies
it into ``os.environ`` at import, and ``Settings()`` reads it each time it is
built. A provider key exported in the developer's shell reaches it through
``os.environ`` directly, so "no key" tests fail locally while CI, which has no
keys, passes. Each test here runs other tests in a fresh pytest process with
conflicting values, so it fails whenever a leak returns. The values are fake
constants.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
#: Names the fake .env sets; removed from the child's environment so the .env is their only source.
DOTENV = {
    "RETRIEVAL__SIMILARITY_THRESHOLD": "0.0",
    "OPENROUTER_API_KEY": "fake-dotenv-key-0000",
}
#: Provider keys a developer's shell may export.
SHELL_KEYS = {
    "OPENROUTER_API_KEY": "fake-shell-key-1111",
    "ANTHROPIC_API_KEY": "fake-shell-key-2222",
    "OPENAI_COMPATIBLE_API_KEY": "fake-shell-key-3333",
}


def run_pytest(cwd: Path, target: str, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    """Run *target* with pytest from *cwd* with exactly *env* as its environment."""
    env = {k: v for k, v in env.items() if k != "PYTEST_XDIST_WORKER"}
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            "-m",
            "pytest",
            str(REPO / target),
            "-q",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(REPO),
            "-c",
            str(REPO / "pyproject.toml"),
            "-n",
            "0",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def assert_one_passed(done: subprocess.CompletedProcess[str]) -> None:
    # Report only the counts line: a failing child may print values from its environment.
    summary = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else done.stderr[-300:]
    assert done.returncode == 0, summary
    assert "1 passed" in summary


@pytest.mark.parametrize(
    "target",
    [
        # Leak through os.environ: a .env retrieval value beat omrg.jsonc.
        "tests/unit/test_settings_file.py::test_one_bad_value_does_not_drop_the_good_ones",
        # Leak through Settings(env_file=".env"): a .env key beat the key file.
        "tests/unit/test_cli_config_show.py::test_key_file_key_shows_last_four_and_key_file",
    ],
)
def test_a_dotenv_in_the_working_folder_does_not_leak_into_tests(
    tmp_path: Path, target: str
) -> None:
    (tmp_path / ".env").write_text(
        "".join(f"{name}={value}\n" for name, value in DOTENV.items()), encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k not in DOTENV}
    assert_one_passed(run_pytest(tmp_path, target, env))


@pytest.mark.parametrize(
    "target",
    [
        # Each test expects no key: OpenRouter, Anthropic, then OpenAI-compatible
        # and Anthropic. None needs fastapi, so they also run in the clean base.
        "tests/unit/test_compose_providers.py::test_a_missing_keychain_entry_says_so_and_leaves_no_key",
        "tests/unit/test_cli_config_show.py::test_unset_key_says_not_set",
        "tests/unit/test_llm_new_providers.py::test_openai_compatible_default_address",
    ],
)
def test_a_provider_key_in_the_shell_does_not_leak_into_tests(tmp_path: Path, target: str) -> None:
    assert_one_passed(run_pytest(tmp_path, target, {**os.environ, **SHELL_KEYS}))
