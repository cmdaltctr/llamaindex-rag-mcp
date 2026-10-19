"""Local access policy for the web transport (design D8).

The server binds to loopback only. A browser proves it was opened from the
launch terminal by posting a one-time bootstrap secret, which the launch URL
carries in its fragment (fragments never reach the server or its access
log). The server answers with an HttpOnly, SameSite=Strict session cookie.
Notebook clients use revocable per-launch bearer credentials limited to the
``graph``, ``read`` and ``run`` scopes. A bearer credential can be bound to
one approved experiment context (design D10). A bound credential reaches
only the graph, run and template routes (:data:`EXPERIMENT_BEARER_PATHS`);
it never reads the live library. Run admission then keeps it inside its
own context.

All credentials live in memory for one launch. Only SHA-256 digests of
session and bearer secrets are kept. :class:`RedactingFilter` removes
credential values from log records.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request

from ...core.vectordb.identity import _MIN_REDACTED_PREFIX_LEN
from .origins import parse_extra_origin
from .secret_set import SecretSet

SESSION_COOKIE = "omrg_session"
BOOTSTRAP_PREFIX = "omrg_bs_"
SESSION_PREFIX = "omrg_ss_"
BEARER_PREFIX = "omrg_bt_"

#: Scopes a bearer credential may hold. Plugin administration, file
#: grants and credential management stay with the browser session.
BEARER_SCOPES: frozenset[str] = frozenset({"graph", "read", "run"})
#: Every scope a route may require; the browser session holds all of them.
#: ``manage`` guards preview-bound destructive actions (delete, profile change).
SESSION_SCOPES: frozenset[str] = BEARER_SCOPES | {"files", "plugins", "credentials", "manage"}
SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
#: Route prefixes an experiment-bound bearer credential may use. Every other
#: route (collections, search, answer, chunks) reads the live library.
EXPERIMENT_BEARER_PATHS: tuple[str, ...] = (
    "/v1/session",
    "/v1/pipeline-operations",
    "/v1/pipeline-templates",
    "/v1/pipelines",
    "/v1/runs",
)

#: Failed bootstrap attempts after which the secret stops working.
MAX_BOOTSTRAP_FAILURES = 20

_LOOPBACK_NAMES = {"localhost": "127.0.0.1"}


def validate_bind_host(host: str) -> str:
    """Return the loopback address to bind, or refuse a remote address.

    Args:
        host: The requested bind address or ``localhost``.

    Returns:
        The literal loopback address to bind.

    Raises:
        ValueError: The address is not a loopback address.
    """
    candidate = _LOOPBACK_NAMES.get(host.strip().lower(), host.strip())
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is None or not address.is_loopback:
        raise ValueError(
            f"Refusing to bind to {host!r}: the web workspace is for local use and "
            "binds only to a loopback address (127.0.0.1, ::1 or localhost). "
            "Use an SSH tunnel if you need to reach it from another machine."
        )
    return str(address)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


@dataclass(frozen=True)
class Principal:
    """An authenticated caller.

    Attributes:
        kind: ``"session"`` (browser) or ``"bearer"`` (notebook client).
        scopes: Scopes the caller holds.
        credential_id: Bearer credential identifier, or ``None`` for a session.
        experiment_context: Experiment context the bearer credential is
            bound to, or ``None`` (a session, or an unbound credential).
    """

    kind: str
    scopes: frozenset[str]
    credential_id: str | None = None
    experiment_context: str | None = None


@dataclass(frozen=True)
class IssuedBearer:
    """A new bearer credential. ``token`` is shown once and never stored."""

    id: str
    token: str
    scopes: frozenset[str]
    label: str
    experiment_context: str | None = None


@dataclass
class _BearerEntry:
    digest: bytes
    scopes: frozenset[str]
    label: str
    created_at: float
    revoked: bool = False
    experiment_context: str | None = None


class AccessPolicy:
    """Per-launch credentials and the Host/Origin rules of one server."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        bootstrap_secret: str,
        extra_origins: Iterable[str] = (),
    ) -> None:
        """Create a policy for a server bound to *host* and *port*.

        Args:
            host: The loopback address the server binds.
            port: The bound TCP port.
            bootstrap_secret: The one-time bootstrap secret.
            extra_origins: Extra loopback browser origins the operator
                approved with ``--allow-origin``. Only ``Origin`` is relaxed;
                ``Host`` and fetch-metadata checks stay as they are.

        Raises:
            ValueError: An extra origin is malformed or not a loopback origin.
        """
        self.host = host
        self.port = port
        self._bootstrap = bootstrap_secret
        self._bootstrap_used = False
        self._bootstrap_failures = 0
        self._sessions: set[bytes] = set()
        self._bearers: dict[str, _BearerEntry] = {}
        self._lock = Lock()
        names = {"127.0.0.1", "localhost", "[::1]"}
        names.add(f"[{host}]" if ":" in host else host)
        self._host_names = frozenset(names)
        own = {f"http://{name}:{port}" for name in names}
        self._origins = frozenset(own | {parse_extra_origin(value) for value in extra_origins})

    @classmethod
    def for_launch(cls, host: str, port: int, *, extra_origins: Iterable[str] = ()) -> AccessPolicy:
        """Create a policy with a fresh random bootstrap secret."""
        return cls(
            host,
            port,
            bootstrap_secret=BOOTSTRAP_PREFIX + secrets.token_urlsafe(32),
            extra_origins=extra_origins,
        )

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """``Host`` header values (name and port) this server answers to."""
        return frozenset(f"{name}:{self.port}" for name in self._host_names)

    @property
    def allowed_origins(self) -> frozenset[str]:
        """``Origin`` values of this server's own pages."""
        return self._origins

    @property
    def cookie_name(self) -> str:
        """Session cookie name. Cookies ignore ports, so the name carries it."""
        return f"{SESSION_COOKIE}_{self.port}"

    @property
    def bootstrap_secret(self) -> str:
        """The bootstrap secret, for the launch URL only."""
        return self._bootstrap

    def launch_url(self) -> str:
        """Return the browser URL; the secret travels in the fragment."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}/#bootstrap={self._bootstrap}"

    # ── Host and Origin ────────────────────────────────────────────

    def host_allowed(self, header: str | None) -> bool:
        """Check a ``Host`` header against the bound loopback names and port."""
        if not header:
            return False
        name, sep, port = header.strip().lower().rpartition(":")
        return bool(sep) and name in self._host_names and port == str(self.port)

    def origin_allowed(self, origin: str | None) -> bool:
        """Check an ``Origin`` header against this server's own origins."""
        return origin is not None and origin.strip().lower() in self._origins

    # ── Bootstrap and session ──────────────────────────────────────

    def exchange_bootstrap(self, candidate: str) -> str | None:
        """Exchange the bootstrap secret once for a new session token.

        Args:
            candidate: The secret the browser posted.

        Returns:
            The session token, or ``None`` when the secret is wrong, used,
            or disabled after too many failures.
        """
        with self._lock:
            if self._bootstrap_used or self._bootstrap_failures >= MAX_BOOTSTRAP_FAILURES:
                return None
            if not hmac.compare_digest(_digest(candidate), _digest(self._bootstrap)):
                self._bootstrap_failures += 1
                return None
            self._bootstrap_used = True
            token = SESSION_PREFIX + secrets.token_urlsafe(32)
            self._sessions.add(_digest(token))
            return token

    def authenticate_session(self, token: str | None) -> Principal | None:
        """Return the session principal for a cookie value, if valid."""
        if not token or _digest(token) not in self._sessions:
            return None
        return Principal("session", SESSION_SCOPES)

    # ── Bearer credentials ─────────────────────────────────────────

    def issue_bearer(
        self, scopes: Iterable[str], label: str = "", *, experiment_context: str | None = None
    ) -> IssuedBearer:
        """Issue a scoped bearer credential, optionally bound to an experiment context.

        The caller checks that *experiment_context* names an active context
        before it calls this method. Revoking the context later does not
        revoke the credential: run admission then refuses it.

        Args:
            scopes: Requested scopes, a subset of :data:`BEARER_SCOPES`.
            label: Display label (cut to 80 characters).
            experiment_context: Context id to bind, or ``None``.

        Raises:
            ValueError: No scopes, or a scope outside :data:`BEARER_SCOPES`.
        """
        wanted = frozenset(scopes)
        if not wanted or not wanted <= BEARER_SCOPES:
            allowed = ", ".join(sorted(BEARER_SCOPES))
            raise ValueError(f"Bearer credentials may hold only these scopes: {allowed}.")
        credential_id = secrets.token_hex(8)
        token = f"{BEARER_PREFIX}{credential_id}.{secrets.token_urlsafe(32)}"
        with self._lock:
            self._bearers[credential_id] = _BearerEntry(
                _digest(token),
                wanted,
                label[:80],
                time.time(),
                experiment_context=experiment_context,
            )
        return IssuedBearer(credential_id, token, wanted, label[:80], experiment_context)

    def authenticate_bearer(self, token: str) -> Principal | None:
        """Return the bearer principal for a token, if valid and not revoked."""
        if not token.startswith(BEARER_PREFIX):
            return None
        credential_id = token[len(BEARER_PREFIX) :].partition(".")[0]
        entry = self._bearers.get(credential_id)
        if entry is None or entry.revoked:
            return None
        if not hmac.compare_digest(entry.digest, _digest(token)):
            return None
        return Principal("bearer", entry.scopes, credential_id, entry.experiment_context)

    def revoke_bearer(self, credential_id: str) -> bool:
        """Revoke a bearer credential. Returns ``False`` for an unknown id."""
        with self._lock:
            entry = self._bearers.get(credential_id)
            if entry is None:
                return False
            entry.revoked = True
            return True

    def list_bearers(self) -> list[dict[str, Any]]:
        """Describe issued bearer credentials without their secrets."""
        return [
            {
                "id": credential_id,
                "scopes": sorted(entry.scopes),
                "label": entry.label,
                "created_at": entry.created_at,
                "revoked": entry.revoked,
                "experiment_context": entry.experiment_context,
            }
            for credential_id, entry in self._bearers.items()
        ]


# ── Request authentication ─────────────────────────────────────────────


def _authenticate(policy: AccessPolicy, request: Request) -> Principal:
    """Authenticate *request* by bearer header or session cookie."""
    challenge = {"WWW-Authenticate": "Bearer"}
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        principal = (
            policy.authenticate_bearer(token.strip()) if scheme.lower() == "bearer" else None
        )
        if principal is None:
            raise HTTPException(401, "The bearer credential is invalid or revoked.", challenge)
        return principal
    principal = policy.authenticate_session(request.cookies.get(policy.cookie_name))
    if principal is None:
        raise HTTPException(401, "Authentication required.", challenge)
    if request.method not in SAFE_METHODS and not policy.origin_allowed(
        request.headers.get("origin")
    ):
        # Cookie-authenticated state changes must prove they come from
        # this application's own pages.
        raise HTTPException(403, "Cross-origin request rejected.")
    return principal


def experiment_path_allowed(path: str, method: str = "GET") -> bool:
    """Return whether an experiment-bound bearer credential may use *path*.

    ``POST /v1/profiles`` is the one profile route allowed: an experiment makes
    a profile to hold its pipelines. The profile list and reads show which
    collections use a profile (``used_by``), which is the live library.
    """
    if path == "/v1/profiles" and method.upper() == "POST":
        return True
    return any(
        path == prefix or path.startswith(prefix + "/") for prefix in EXPERIMENT_BEARER_PATHS
    )


def require_scope(scope: str) -> Callable[[Request], Any]:
    """Build a route dependency that requires *scope*.

    Every protected route, including state-changing and stream routes,
    uses this one dependency, so the same policy guards all of them.

    Args:
        scope: A member of :data:`SESSION_SCOPES`.

    Returns:
        An async FastAPI dependency returning the :class:`Principal`.
    """
    if scope not in SESSION_SCOPES:
        raise ValueError(f"Unknown scope {scope!r}.")

    async def dependency(request: Request) -> Principal:
        principal = _authenticate(request.app.state.access_policy, request)
        if scope not in principal.scopes:
            raise HTTPException(403, f"This credential lacks the {scope!r} scope.")
        if principal.experiment_context is not None and not experiment_path_allowed(
            request.url.path, request.method
        ):
            raise HTTPException(
                403,
                "An experiment credential cannot read or change the live library; "
                "it can use only pipeline, run and template routes, and create a profile.",
            )
        request.state.principal = principal
        return principal

    dependency.omrg_scope = scope  # type: ignore[attr-defined]
    return dependency


# ── Redaction ──────────────────────────────────────────────────────────

_PREFIXED = re.compile(r"\b(omrg_(?:bs|ss|bt|mcp)_)[A-Za-z0-9_.\-]+")
_BEARER = re.compile(r"(?i)\b(bearer\s+)(?!omrg_)[^\s,;\"']+")
_COOKIE = re.compile(r"(omrg_session(?:_\d+)?=)[^;\s\"']+")
_QUERY = re.compile(
    r"(?i)([?&#](?:bootstrap|token|access_token|session|secret|api_key|password)=)[^&#\s\"']+"
)

#: Query-string keys that must never carry a value.
SECRET_QUERY_KEYS: frozenset[str] = frozenset(
    {"bootstrap", "token", "access_token", "session", SESSION_COOKIE, "secret", "api_key"}
)


def redact(text: str, extra: Iterable[str] = ()) -> str:
    """Remove credential values from *text*.

    Args:
        text: Any log or error text.
        extra: Further secret values, such as configured provider keys.

    Returns:
        The text with every credential form replaced by ``***``.
    """
    text = _PREFIXED.sub(r"\1***", text)
    text = _BEARER.sub(r"\1***", text)
    text = _COOKIE.sub(r"\1***", text)
    text = _QUERY.sub(r"\1***", text)
    # One combined list, longest first: the prefix shared by two keys must
    # not cut one of them in half before its longer fragment is matched.
    values = {value for value in extra if value}
    pieces = set(values)
    for value in values:
        for length in range(_MIN_REDACTED_PREFIX_LEN, len(value)):
            pieces.add(value[:length])
    for piece in sorted(pieces, key=len, reverse=True):
        text = text.replace(piece, "***")
    return text


def looks_like_credential(value: str) -> bool:
    """Return whether *value* contains an OMRG credential."""
    return _PREFIXED.search(value) is not None


class RedactingFilter(logging.Filter):
    """Logging filter that removes credentials from messages and tracebacks."""

    def __init__(self, extra: Iterable[str] = ()) -> None:
        """Create the filter.

        Args:
            extra: Further secret values to remove (for example provider keys).
                Pass a :class:`SecretSet` to see keys added later.
        """
        super().__init__()
        self.secrets = extra if isinstance(extra, SecretSet) else SecretSet(extra)

    @property
    def _extra(self) -> tuple[str, ...]:
        """The secrets as they are now. Read at filter time."""
        return tuple(self.secrets)

    def _clean(self, value: Any, extra: tuple[str, ...]) -> Any:
        return redact(value, extra) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact *record* in place; never drop it."""
        extra = self._extra
        if record.exc_info or record.exc_text:
            # Format the traceback now so it can be redacted, then drop
            # the raw exception so no handler formats it again.
            text = record.getMessage()
            trace = record.exc_text or logging.Formatter().formatException(record.exc_info)  # type: ignore[arg-type]
            record.msg = redact(f"{text}\n{trace}", extra)
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            return True
        record.msg = self._clean(record.msg, extra)
        if isinstance(record.args, tuple):
            record.args = tuple(self._clean(arg, extra) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: self._clean(arg, extra) for key, arg in record.args.items()}
        return True


def install_log_redaction(log_filter: RedactingFilter) -> None:
    """Attach *log_filter* to the root handlers and the server loggers.

    Args:
        log_filter: The filter to attach. Attaching twice has no effect.
    """
    targets: list[logging.Filterer] = list(logging.getLogger().handlers)
    targets += [
        logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "omrg")
    ]
    for target in targets:
        if not any(isinstance(item, RedactingFilter) for item in target.filters):
            target.addFilter(log_filter)
