"""Install type, ``uv`` lookup, copy commands and install reasons (tasks 1.1 to 2.1).

Every test builds a fake environment in ``tmp_path``: a ``uv-receipt.toml``
beside a fake prefix, a fake checkout with ``pyproject.toml`` and
``uv.lock``, or neither. No test reads the real home folder or runs ``uv``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omrs.transports.api.install_environment import (
    InstallEnvironment,
    copy_command,
    detect_environment,
    extra_requirements,
    find_uv,
    install_reason,
)

RECEIPT = """\
[tool]
requirements = [{{ name = "omrs", extras = ["web", "hybrid"], {source} }}]
entrypoints = [
    {{ name = "omrs", install-path = "/x/bin/omrs", from = "omrs" }},
]
"""


def _no_uv(_: str) -> None:
    return None


def _package_in(folder: Path) -> Path:
    package = folder / "omrs" / "__init__.py"
    package.parent.mkdir(parents=True)
    package.write_text("", encoding="utf-8")
    return package


def _tool_env(tmp_path: Path, source: str) -> Path:
    prefix = tmp_path / "tools" / "omrs"
    prefix.mkdir(parents=True)
    (prefix / "uv-receipt.toml").write_text(RECEIPT.format(source=source), encoding="utf-8")
    return prefix


def _detect(tmp_path: Path, prefix: Path, package: Path, which=_no_uv) -> InstallEnvironment:
    return detect_environment(prefix=prefix, package_file=package, home=tmp_path, which=which)


# ── 1.1 Install type ─────────────────────────────────────────────────────


def test_a_receipt_beside_the_prefix_is_a_uv_tool_install(tmp_path: Path) -> None:
    source = tmp_path / "src" / "omrs"
    prefix = _tool_env(tmp_path, f'directory = "{source}"')
    package = _package_in(prefix / "lib" / "site-packages")
    env = _detect(tmp_path, prefix, package)
    assert env.install_type == "uv-tool"
    assert env.receipt_extras == ("web", "hybrid")
    assert env.receipt_source == "~/src/omrs"


def test_a_folder_with_pyproject_and_uv_lock_is_a_checkout(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "pyproject.toml").write_text("", encoding="utf-8")
    (project / "uv.lock").write_text("", encoding="utf-8")
    package = _package_in(project / "src")
    env = _detect(tmp_path, project / ".venv", package)
    assert env.install_type == "checkout"


def test_pyproject_without_uv_lock_is_not_a_checkout(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "pyproject.toml").write_text("", encoding="utf-8")
    package = _package_in(project / "src")
    assert _detect(tmp_path, tmp_path / "venv", package).install_type == "other"


def test_neither_receipt_nor_checkout_is_other(tmp_path: Path) -> None:
    package = _package_in(tmp_path / "site-packages")
    env = _detect(tmp_path, tmp_path / "venv", package)
    assert env.install_type == "other"
    assert env.receipt_extras == () and env.receipt_source is None


def test_a_broken_receipt_still_means_uv_tool_without_extras(tmp_path: Path) -> None:
    prefix = tmp_path / "tools" / "omrs"
    prefix.mkdir(parents=True)
    (prefix / "uv-receipt.toml").write_text("not [valid toml", encoding="utf-8")
    env = _detect(tmp_path, prefix, _package_in(tmp_path / "site"))
    assert env.install_type == "uv-tool"
    assert env.receipt_extras == () and env.receipt_source is None


@pytest.mark.parametrize(
    ("source", "expected", "editable"),
    [
        ('editable = "{home}/code/omrs"', "~/code/omrs", True),
        ('git = "https://example.org/omrs.git"', "git+https://example.org/omrs.git", False),
        ('specifier = ">=3"', None, False),
    ],
)
def test_receipt_sources(tmp_path: Path, source: str, expected: str | None, editable: bool) -> None:
    prefix = _tool_env(tmp_path, source.format(home=tmp_path))
    env = _detect(tmp_path, prefix, _package_in(tmp_path / "site"))
    assert env.receipt_source == expected
    assert env.receipt_editable is editable


# ── 1.1 uv lookup ────────────────────────────────────────────────────────


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_uv_on_path_wins(tmp_path: Path) -> None:
    _executable(tmp_path / ".local" / "bin" / "uv")
    assert find_uv(home=tmp_path, which=lambda name: "/opt/uv/bin/uv") == "/opt/uv/bin/uv"


def test_uv_falls_back_to_local_bin_then_cargo_bin(tmp_path: Path) -> None:
    cargo = _executable(tmp_path / ".cargo" / "bin" / "uv")
    assert find_uv(home=tmp_path, which=_no_uv) == str(cargo)
    local = _executable(tmp_path / ".local" / "bin" / "uv")
    assert find_uv(home=tmp_path, which=_no_uv) == str(local)


def test_a_file_that_cannot_run_is_not_uv(tmp_path: Path) -> None:
    plain = tmp_path / ".local" / "bin" / "uv"
    plain.parent.mkdir(parents=True)
    plain.write_text("", encoding="utf-8")
    os.chmod(plain, 0o644)
    assert find_uv(home=tmp_path, which=_no_uv) is None


# ── 1.2 Copy commands ────────────────────────────────────────────────────


def _env(install_type: str, **kwargs: object) -> InstallEnvironment:
    return InstallEnvironment(install_type=install_type, **kwargs)  # type: ignore[arg-type]


def test_uv_tool_command_adds_the_extra_to_the_receipt_extras() -> None:
    env = _env("uv-tool", receipt_extras=("web", "hybrid"), receipt_source="~/src/omrs")
    assert copy_command(env, "anthropic") == (
        'uv tool install --reinstall "omrs[web,hybrid,anthropic] @ ~/src/omrs"'
    )


def test_uv_tool_command_does_not_repeat_an_extra_in_the_receipt() -> None:
    env = _env("uv-tool", receipt_extras=("web", "hybrid"), receipt_source="~/src/omrs")
    assert copy_command(env, "hybrid") == (
        'uv tool install --reinstall "omrs[web,hybrid] @ ~/src/omrs"'
    )


def test_uv_tool_command_keeps_editable_and_works_without_a_source() -> None:
    editable = _env("uv-tool", receipt_extras=("web",), receipt_source="~/x", receipt_editable=True)
    assert copy_command(editable, "azure") == (
        'uv tool install --reinstall --editable "omrs[web,azure] @ ~/x"'
    )
    assert copy_command(_env("uv-tool"), "azure") == 'uv tool install --reinstall "omrs[azure]"'


def test_checkout_and_other_commands() -> None:
    assert copy_command(_env("checkout"), "azure") == "uv sync --extra azure"
    assert copy_command(_env("other"), "azure") == 'pip install "omrs[azure]"'


# ── 1.3 Install reasons ──────────────────────────────────────────────────

TOOL = InstallEnvironment(install_type="uv-tool", uv="/bin/uv")
PACKAGES = ["llama-index-llms-anthropic>=0.11.0"]


def test_an_allowed_missing_extra_is_installable() -> None:
    assert install_reason("anthropic", "not-installed", PACKAGES, TOOL) is None
    assert install_reason("anthropic", "unknown", PACKAGES, TOOL) is None


@pytest.mark.parametrize("extra", ["web", "torch", None])
def test_web_torch_and_always_on_are_not_installable_here(extra: str | None) -> None:
    assert install_reason(extra, "not-installed", PACKAGES, TOOL) == "not-installable-here"


@pytest.mark.parametrize("availability", ["available", "restart-needed"])
def test_an_installed_extra_is_already_installed(availability: str) -> None:
    assert install_reason("anthropic", availability, PACKAGES, TOOL) == "already-installed"


def test_an_extra_without_requirements_has_nothing_to_install() -> None:
    assert install_reason("llamacpp", "not-installed", [], TOOL) == "no-requirements"


def test_a_checkout_or_other_install_is_not_a_uv_tool() -> None:
    for kind in ("checkout", "other"):
        env = InstallEnvironment(install_type=kind, uv="/bin/uv")  # type: ignore[arg-type]
        assert install_reason("anthropic", "not-installed", PACKAGES, env) == "not-uv-tool"


def test_a_uv_tool_install_without_uv_cannot_install() -> None:
    env = InstallEnvironment(install_type="uv-tool", uv=None)
    assert install_reason("anthropic", "not-installed", PACKAGES, env) == "uv-not-found"


# ── 2.1 Requirements from the installed metadata ─────────────────────────


def test_anthropic_requirements_come_from_the_installed_metadata() -> None:
    assert extra_requirements("anthropic") == ["llama-index-llms-anthropic>=0.11.0"]


def test_an_unknown_extra_has_no_requirements() -> None:
    assert extra_requirements("anthropic; rm -rf ~") == []
    assert extra_requirements("no-such-extra") == []


def test_other_marker_parts_are_kept_and_other_extras_ignored() -> None:
    requires = [
        "a>=1; extra == 'x'",
        'b<2; python_version < "3.12" and extra == "x"',
        "c; extra == 'y'",
        "d",
    ]
    assert extra_requirements("x", requires) == ["a>=1", 'b<2; python_version < "3.12"']
