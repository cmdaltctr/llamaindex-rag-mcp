"""A developer's ``.env`` must not reach a test (fix/settings-file-test-isolation).

A ``.env`` in the working folder reaches a test two ways: ``omrg.config`` copies
it into ``os.environ`` at import, and ``Settings()`` reads it each time it is
built. Each test here runs other tests in a fresh pytest process from a folder
whose ``.env`` sets conflicting values, so it fails whenever either leak returns.
The values are fake constants.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
#: Names the fake .env sets; removed from the child's environment so the .env is their only source.
DOTENV = {
    "RETRIEVAL__SIMILARITY_THRESHOLD": "0.0",
    "OPENROUTER_API_KEY": "fake-dotenv-key-0000",
}


def run_in_folder_with_dotenv(tmp_path: Path, target: str) -> subprocess.CompletedProcess[str]:
    """Run *target* with pytest from a folder whose ``.env`` holds :data:`DOTENV`."""
    (tmp_path / ".env").write_text(
        "".join(f"{name}={value}\n" for name, value in DOTENV.items()), encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k not in DOTENV}
    env.pop("PYTEST_XDIST_WORKER", None)
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
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


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
    done = run_in_folder_with_dotenv(tmp_path, target)
    # Report only the counts line: a failing child may print values from its environment.
    summary = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else done.stderr[-300:]
    assert done.returncode == 0, summary
    assert "1 passed" in summary
