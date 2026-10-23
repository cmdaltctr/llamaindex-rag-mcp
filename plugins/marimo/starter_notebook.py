"""OMRS starter notebook for marimo (design D10, task 8.6).

Open this file with the registered marimo plugin, inside an approved
experiment workspace. The notebook submits graph runs through the same
protected OMRS graph API as the canvas, in one experiment context only.

When OMRS opens the editor, the notebook connects by itself. OMRS
writes a private connection file, ``omrs_connection.json`` (mode 600),
into the editor's private launch directory and sets ``OMRS_CONNECTION_FILE`` to its path. The file
holds the API address, the experiment context id and the path of a
separate private token file. That token is a new bearer credential bound
to the experiment context. OMRS revokes it and deletes both files when
the editor stops.

For an editor that you start yourself, set these environment variables
in its shell instead (the notebook never stores or prints the token):

* ``OMRS_API_URL``: the loopback server address, for example
  ``http://127.0.0.1:8765``.
* ``OMRS_TOKEN_FILE``: a private file (mode 600) that holds a bearer
  credential bound to the experiment context. ``OMRS_TOKEN`` also works.
* ``OMRS_EXPERIMENT_CONTEXT``: the experiment context id (``exp_...``).

``OMRS_CONNECTION_FILE`` takes precedence over these variables. The
notebook refuses a connection file or a token file that other users can
read or that has any mode bit wider than 600.

Nothing runs when the notebook opens. Change the parameters, then press
**Run graph**. Each run records the graph revision, the effective
settings, the backend and index identity, the inputs and the outputs, and
writes a checkpoint below ``output/runs/`` (temporary file, then rename).

Trust: notebook Python runs with your user account's filesystem and
network permissions. A dependency environment is not an operating-system
sandbox.

The helper functions below use the standard library only. The file keeps
marimo's layout, so ``marimo check`` accepts it.
"""

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import hashlib
    import json
    import os
    import re
    import stat
    import time
    import urllib.error
    import urllib.parse
    import urllib.request
    from pathlib import Path


@app.class_definition
class ApiConfigError(RuntimeError):
    """The notebook connection settings are missing or unsafe."""


@app.class_definition
class ApiError(RuntimeError):
    """The OMRS API refused a request. The message never holds a credential."""

    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self.body = body if isinstance(body, dict) else {}
        self.code = self.body.get("code")
        message = str(self.body.get("message") or "no message")
        suffix = f" ({self.code})" if self.code else ""
        super().__init__(f"OMRS API returned {status}: {message}{suffix}")


@app.function
def urllib_transport(method: str, url: str, body: object, headers: dict) -> tuple:
    """Send one JSON request with the standard library; return ``(status, body)``."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - the client allows loopback http only
        url,
        data=data,
        method=method,
        headers={**headers, "Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except ValueError:
            return exc.code, None


@app.function
def check_loopback_url(base_url: str) -> str:
    """Return *base_url* without a trailing slash; refuse a non-loopback address."""
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ApiConfigError(
            "OMRS_API_URL must be the loopback address that `omrs web` printed, "
            "for example http://127.0.0.1:8765."
        )
    return base_url.rstrip("/")


@app.function
def read_private_file(path: Path, label: str) -> str:
    """Return the text of a file that is private to its owner.

    The file mode must be 600 or narrower. A wider mode (for example 644
    or 700) is refused.
    """
    try:
        mode = stat.S_IMODE(Path(path).stat().st_mode)
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        raise ApiConfigError(f"{label} cannot be read.") from None
    if mode & ~0o600:
        raise ApiConfigError(f"{label} must be private: run chmod 600 on it.")
    return text


@app.function
def connection_from_file(environ: dict):
    """Return ``{api_url, experiment_context, token}`` from ``OMRS_CONNECTION_FILE``.

    Returns ``None`` when the variable is not set. OMRS sets it when it
    opens the editor.
    """
    path = environ.get("OMRS_CONNECTION_FILE", "").strip()
    if not path:
        return None
    text = read_private_file(Path(path), "OMRS_CONNECTION_FILE")
    try:
        details = json.loads(text)
    except ValueError:
        details = None
    keys = ("api_url", "experiment_context", "token_file")
    if not isinstance(details, dict) or not all(
        isinstance(details.get(key), str) and details[key].strip() for key in keys
    ):
        raise ApiConfigError(
            "OMRS_CONNECTION_FILE must hold api_url, experiment_context and token_file. "
            "Stop the editor and open it again from OMRS."
        )
    token = read_private_file(Path(details["token_file"]), "The connection token file").strip()
    if not token:
        raise ApiConfigError("The connection token file is empty. Open the editor again.")
    return {
        "api_url": details["api_url"],
        "experiment_context": details["experiment_context"].strip(),
        "token": token,
    }


@app.function
def read_token(environ: dict) -> str:
    """Return the bearer token from ``OMRS_TOKEN_FILE`` or ``OMRS_TOKEN``.

    A token file must be private to its owner (mode 600).
    """
    path = environ.get("OMRS_TOKEN_FILE")
    if path:
        text = read_private_file(Path(path), "OMRS_TOKEN_FILE").strip()
        if text:
            return text
    token = environ.get("OMRS_TOKEN", "").strip()
    if not token:
        raise ApiConfigError(
            "Set OMRS_TOKEN_FILE (or OMRS_TOKEN) to a bearer credential that is bound "
            "to the experiment context. Issue it in the OMRS Experiments view."
        )
    return token


@app.class_definition
class ApiClient:
    """Minimal OMRS API client. ``repr`` and errors never show the token."""

    def __init__(self, base_url: str, token: str, *, transport=None) -> None:
        self.base_url = check_loopback_url(base_url)
        self._token = token
        self._transport = transport or urllib_transport

    def __repr__(self) -> str:
        return f"ApiClient({self.base_url!r}, token=<hidden>)"

    @classmethod
    def from_environment(cls, environ=None, *, transport=None):
        """Build a client from ``OMRS_CONNECTION_FILE``, else ``OMRS_API_URL`` and the token."""
        env = os.environ if environ is None else environ
        connection = connection_from_file(env)
        if connection is not None:
            return cls(connection["api_url"], connection["token"], transport=transport)
        base_url = env.get("OMRS_API_URL")
        if not base_url:
            raise ApiConfigError("Set OMRS_API_URL to the address that `omrs web` printed.")
        return cls(base_url, read_token(env), transport=transport)

    def request(self, method: str, path: str, body: object = None) -> object:
        """Send one request; raise :class:`ApiError` for a refusal."""
        headers = {"Authorization": f"Bearer {self._token}"}
        status, payload = self._transport(method, self.base_url + path, body, headers)
        if status >= 400:
            raise ApiError(status, payload)
        return payload


@app.function
def experiment_context_from_environment(environ=None) -> str:
    """Return the context id from ``OMRS_CONNECTION_FILE``, else ``OMRS_EXPERIMENT_CONTEXT``."""
    env = os.environ if environ is None else environ
    connection = connection_from_file(env)
    if connection is not None:
        return connection["experiment_context"]
    context_id = env.get("OMRS_EXPERIMENT_CONTEXT", "").strip()
    if not context_id:
        raise ApiConfigError("Set OMRS_EXPERIMENT_CONTEXT to the experiment context id.")
    return context_id


@app.function
def list_templates(client: ApiClient) -> list:
    """Return the canonical templates (``GET /v1/pipeline-templates``)."""
    return client.request("GET", "/v1/pipeline-templates")["templates"]


@app.function
def set_node_params(document: dict, params: dict) -> dict:
    """Return a copy of *document* with ``{node_id: {name: value}}`` merged into node params."""
    copy = json.loads(json.dumps(document))
    nodes = {node["id"]: node for node in copy["nodes"]}
    for node_id, values in params.items():
        if node_id not in nodes:
            raise KeyError(f"The graph has no node {node_id!r}.")
        nodes[node_id]["params"] = {**(nodes[node_id].get("params") or {}), **values}
    return copy


@app.function
def document_digest(document: dict) -> str:
    """Return a stable SHA-256 of a graph document."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@app.function
def experiment_record(revision: dict, run: dict, events: list, result: object) -> dict:
    """Return what one run records: revision, settings, identity, inputs and outputs."""
    resources = run.get("resources") or {}
    experiment = resources.get("experiment") or {}
    backend = experiment.get("backend") or {}
    result = result if isinstance(result, dict) else {}
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "failure": run.get("failure"),
        "graph_revision": {
            "pipeline_id": revision["pipeline_id"],
            "revision_id": revision["revision_id"],
            "graph_hash": run["graph_hash"],
            "graph_identity": resources.get("graph_identity"),
        },
        "experiment_context": experiment.get("context_id"),
        "effective_settings": run.get("settings"),
        "backend": backend,
        "index_identity": backend.get("index_identity"),
        "inputs": run.get("inputs"),
        "outputs": result.get("outputs"),
        "result_ref": run.get("result_ref"),
        "event_count": len(events),
        "wall_time_s": result.get("wall_time_s"),
    }


@app.function
def checkpoint(record: dict, output_dir: Path, name: str) -> Path:
    """Write *record* to ``<output_dir>/<name>.json`` atomically (temporary file, then rename)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:120] or "run"
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / f"{safe}.json"
    temporary = folder / f"{safe}.json.tmp"
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, final)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return final


@app.class_definition
class ExperimentSession:
    """Explicit-run graph experiments in one experiment context.

    The session creates one profile once (its pipelines hold the graphs) and
    saves a revision only for a new graph document. A run happens only when the caller passes
    ``run_requested=True`` (the notebook's Run button), so a parameter
    change alone admits nothing.
    """

    def __init__(
        self,
        client: ApiClient,
        experiment_context: str,
        output_dir: Path,
        *,
        title: str = "Notebook experiment",
        poll_interval: float = 0.5,
        timeout: float = 600.0,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.client = client
        self.experiment_context = experiment_context
        self.output_dir = Path(output_dir)
        self.title = title
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._profile = None
        self._revisions: dict = {}
        self.runs_submitted = 0

    @staticmethod
    def slot_for(document: dict) -> str:
        """Return the profile slot a graph fits: ``ingest``, ``answer`` or ``search``."""
        inputs = {item.get("name") for item in document.get("inputs") or []}
        outputs = {item.get("name") for item in document.get("outputs") or []}
        if "path" in inputs:
            return "ingest"
        return "answer" if "answer" in outputs else "search"

    def revision_for(self, document: dict) -> dict:
        """Return the saved revision of *document*; save it once.

        The first call creates one profile for this session. Its base is the
        profile the first graph names (``codebase``), else ``documents``. A
        graph with no profile gets the base. Each graph is saved in the slot
        pipeline that fits its inputs and outputs.
        """
        if self._profile is None:
            base = document.get("profile")
            base = base if base in ("documents", "codebase") else "documents"
            body = {"title": self.title, "source": base}
            self._profile = self.client.request("POST", "/v1/profiles", body)["profile"]
        document = {**document, "profile": document.get("profile") or self._profile["base_profile"]}
        digest = document_digest(document)
        if digest not in self._revisions:
            pipeline_id = self._profile["slots"][self.slot_for(document)]
            path = f"/v1/pipelines/{pipeline_id}/revisions"
            saved = self.client.request("POST", path, {"document": document})
            self._revisions[digest] = saved["revision"]
        return self._revisions[digest]

    def submit(self, revision: dict, inputs: dict) -> dict:
        """Submit one run of *revision* in the experiment context."""
        body = {
            "revision_id": revision["revision_id"],
            "inputs": inputs,
            "experiment_context": self.experiment_context,
        }
        run = self.client.request("POST", "/v1/runs", body)["run"]
        self.runs_submitted += 1
        return run

    def follow(self, run_id: str) -> tuple:
        """Poll events until the run ends; return the final run and its events."""
        events: list = []
        after = 0
        deadline = self._clock() + self.timeout
        while True:
            page = self.client.request("GET", f"/v1/runs/{run_id}/events?after_sequence={after}")
            events.extend(page["events"])
            after = page["last_sequence"]
            if page["complete"]:
                break
            if self._clock() > deadline:
                raise TimeoutError(
                    f"Run {run_id} did not finish in {self.timeout} s. It continues on the "
                    f"server; cancel it with POST /v1/runs/{run_id}/cancel."
                )
            self._sleep(self.poll_interval)
        return self.client.request("GET", f"/v1/runs/{run_id}")["run"], events

    def result(self, run: dict) -> object:
        """Return the stored result of a finished run, or ``None``."""
        try:
            return self.client.request("GET", f"/v1/runs/{run['run_id']}/result")["result"]
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise

    def run(self, document: dict, inputs: dict, *, run_requested: bool, name: str = "run"):
        """Run *document* once when explicitly requested; checkpoint the record.

        Returns:
            The run record with its checkpoint path, or ``None`` when no run
            was requested.

        Raises:
            ApiError: The server refused the run (for example a revoked
                context or credential). No checkpoint is written.
        """
        if not run_requested:
            return None
        revision = self.revision_for(document)
        run, events = self.follow(self.submit(revision, inputs)["run_id"])
        record = experiment_record(revision, run, events, self.result(run))
        path = checkpoint(record, self.output_dir, f"{name}-{run['run_id']}")
        return {**record, "checkpoint": str(path)}


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # OMRS experiment

    This notebook runs OMRS graphs in one approved experiment context.
    Nothing runs until you press **Run graph**.

    **Trust:** notebook Python runs with your user account's filesystem
    and network permissions. A dependency environment is not an
    operating-system sandbox.
    """)
    return


@app.cell
def _(mo):
    client = ApiClient.from_environment()
    session = ExperimentSession(
        client,
        experiment_context_from_environment(),
        mo.notebook_dir() / "output" / "runs",
    )
    mo.md(f"Server `{client.base_url}`, experiment context `{session.experiment_context}`.")
    return (session,)


@app.cell
def _(mo, session):
    templates = {template["name"]: template for template in list_templates(session.client)}
    template_picker = mo.ui.dropdown(options=templates, value="search", label="Template")
    template_picker  # noqa: B018 - marimo displays the last expression
    return (template_picker,)


@app.cell
def _(mo):
    query = mo.ui.text(value="", label="Query")
    top_k = mo.ui.number(start=1, stop=100, value=10, label="top_k")
    mo.hstack([query, top_k])
    return query, top_k


@app.cell
def _(mo):
    run_button = mo.ui.run_button(label="Run graph")
    run_button  # noqa: B018 - marimo displays the last expression
    return (run_button,)


@app.cell
def _(mo, query, run_button, session, template_picker, top_k):
    mo.stop(
        not run_button.value,
        mo.md("Change the parameters, then press **Run graph**. Nothing runs before that."),
    )
    document = set_node_params(
        template_picker.value["document"], {"prepare": {"top_k": top_k.value}}
    )
    record = session.run(
        document,
        {"query": query.value},
        run_requested=True,
        name=template_picker.value["name"],
    )
    return (record,)


@app.cell
def _(mo, record):
    mo.vstack(
        [
            mo.md(
                f"Run `{record['run_id']}`: **{record['status']}**. "
                f"Index `{record['index_identity']}`. Checkpoint `{record['checkpoint']}`."
            ),
            mo.json(record),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
