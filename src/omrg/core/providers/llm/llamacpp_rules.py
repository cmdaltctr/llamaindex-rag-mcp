"""Launch rules of the llama.cpp server that ``omrg web`` manages (design D12).

Pure checks and builders. Nothing here starts a process. The lifecycle module
in ``transports/api`` calls these before every launch and again at save time,
so a program, a model or a port that fails a rule never reaches ``Popen``.

The rules keep the launch narrow on purpose:

* the program is an absolute path to an executable regular file whose name is
  exactly ``llama-server``, both as given and after links are resolved;
* the model is an existing ``.gguf`` file or a Hugging Face id, and never
  starts with ``-``;
* the port comes from a loopback ``http`` chat URL and the server binds
  ``127.0.0.1`` only;
* the argument list holds fixed flags and nothing else;
* the child gets four environment variables, plus three cache and token
  variables for a Hugging Face model, and never a provider key.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from .connection import ConnectionField

#: Whether file names follow Windows rules. Tests set this to check ``.exe``.
IS_WINDOWS = os.name == "nt"

#: Fixed failure reasons of the managed server (design D12).
REASONS = (
    "binary-invalid",
    "model-invalid",
    "not-loopback",
    "port-in-use",
    "exited",
    "timeout",
    "not-configured",
)

#: Longest accepted program or model text.
MAX_TEXT_CHARS = 2048

_HF_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}(:[A-Za-z0-9._-]{1,64})?"
)
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
#: Always passed to the child, when set.
BASE_ENVIRONMENT = ("PATH", "HOME", "LANG", "TMPDIR")
#: Passed only for a Hugging Face model, and only when already set.
HUGGING_FACE_ENVIRONMENT = ("LLAMA_CACHE", "HF_HOME", "HF_TOKEN")

ModelKind = Literal["file", "hf"]

#: Settings of the managed server. They are not part of any provider
#: descriptor: the card shows them in its own "Local server" block.
LLAMACPP_SERVER_FIELDS: tuple[ConnectionField, ...] = (
    ConnectionField(
        "server_binary", "Program path", "text", "llamacpp_server_binary", "LLAMACPP_SERVER_BINARY"
    ),
    ConnectionField(
        "server_model", "Model", "text", "llamacpp_server_model", "LLAMACPP_SERVER_MODEL"
    ),
    ConnectionField(
        "context_window",
        "Context window (tokens)",
        "int",
        "llamacpp_context_window",
        "LLAMACPP_CONTEXT_WINDOW",
        minimum=2048,
        maximum=262144,
    ),
)


def binary_names() -> frozenset[str]:
    """Return the only file name the program may have on this platform."""
    return frozenset({"llama-server.exe" if IS_WINDOWS else "llama-server"})


def check_binary(path: str) -> bool:
    """Return whether *path* is a program that may be launched.

    The path must be absolute, name a regular file that the user can run, and
    end in exactly ``llama-server`` (``llama-server.exe`` on Windows) both as
    given and after links are resolved. A link named ``llama-server`` that
    points at a shell fails the second test.

    Args:
        path: The program path as saved.

    Returns:
        ``True`` when every rule holds now. The file is read at call time, so a
        file replaced after a save fails here.
    """
    if not path or len(path) > MAX_TEXT_CHARS or "\x00" in path or not os.path.isabs(path):
        return False
    names = binary_names()
    if os.path.basename(path) not in names:
        return False
    try:
        resolved = Path(path).resolve(strict=True)
        info = resolved.stat()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved.name in names and stat.S_ISREG(info.st_mode) and os.access(resolved, os.X_OK)


def model_kind(value: str) -> ModelKind | None:
    """Return ``file`` or ``hf`` when *value* is an allowed model, else ``None``.

    ``file`` is an absolute path to an existing file that ends in ``.gguf``.
    ``hf`` is a Hugging Face id ``org/name`` with an optional ``:tag``. A value
    that starts with ``-`` is never accepted, so it cannot act as a flag.
    """
    if not value or value != value.strip() or len(value) > MAX_TEXT_CHARS or "\x00" in value:
        return None
    if value.startswith("-"):
        return None
    if os.path.isabs(value):
        path = Path(value)
        if path.suffix.lower() == ".gguf" and path.is_file():
            return "file"
        return None
    return "hf" if _HF_ID.fullmatch(value) else None


def chat_port(url: str) -> int | None:
    """Return the port of a loopback ``http`` chat URL, or ``None`` when it is not one.

    The host must be ``127.0.0.1``, ``localhost`` or ``::1`` exactly. A URL
    with a user name, another scheme or a port outside 1 to 65535 gives
    ``None``. A URL with no port means port 80.
    """
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "http" or host not in _LOOPBACK or parts.username is not None:
        return None
    number = 80 if port is None else port
    return number if 1 <= number <= 65535 else None


def build_argv(binary: str, model: str, kind: ModelKind, port: int, window: int) -> list[str]:
    """Return the argument list: fixed flags and the checked values, nothing else."""
    flag = "-m" if kind == "file" else "-hf"
    return [binary, flag, model, "--host", "127.0.0.1", "--port", str(port), "-c", str(window)]


def child_environment(environ: Mapping[str, str], kind: ModelKind) -> dict[str, str]:
    """Return the environment of the child process.

    Args:
        environ: The environment of ``omrg web``.
        kind: The model kind. Only a Hugging Face model gets the cache and
            token variables.

    Returns:
        The allowed variables that *environ* holds. No provider API key is ever
        in the result.
    """
    names = BASE_ENVIRONMENT + (HUGGING_FACE_ENVIRONMENT if kind == "hf" else ())
    return {name: environ[name] for name in names if name in environ}
