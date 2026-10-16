"""Canonical pipeline templates (task 4.5 templates over HTTP, task 8.6).

``GET /v1/pipeline-templates`` returns the templates shaped for the live
Engine by ``compose_pipelines.pipeline_templates``: the retrieval chain
is hybrid when the collection settings enable it, and the rerank node
starts bypassed when the Engine has no reranker. Each document is an
editable graph; save a copy as a revision before a run.

Graph outputs carry summaries and results only. The ``search`` output is
a ``ContextBundle``; a stored run result holds its public rows (the
``Engine.search`` row shape, from ``ContextBundle.public_rows()``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ..engine_access import ReadScope, RuntimeDep, admitted
from .graphs import ok

router = APIRouter(prefix="/v1")

#: What each template output holds, by template name.
OUTPUT_DESCRIPTIONS: dict[str, str] = {
    "ingestion": "Commit summary for each source unit (CommitSummary).",
    "search": (
        "Assembled context (ContextBundle). A stored run result holds its public "
        "rows, the Engine.search row shape (ContextBundle.public_rows())."
    ),
    "answer": "Answer result: answer text, citations, evidence and verification.",
}


def describe_templates(engine: Any) -> list[dict[str, Any]]:
    """Return the Engine's canonical templates as JSON-ready entries."""
    from ....compose_pipelines import pipeline_templates

    entries = []
    for template in pipeline_templates(engine):
        graph = template.definition.graph
        description = OUTPUT_DESCRIPTIONS.get(template.name, "")
        entries.append(
            {
                "name": template.name,
                "title": template.title,
                "description": template.description,
                "standard_operation": template.standard_operation,
                "document": graph.model_dump(mode="json"),
                "outputs": [
                    {"name": output.name, "description": description} for output in graph.outputs
                ],
            }
        )
    return entries


@router.get("/pipeline-templates", operation_id="listPipelineTemplates")
async def list_pipeline_templates(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return the canonical ingestion, search and answer templates."""
    async with admitted(runtime):
        templates = await run_in_threadpool(describe_templates, runtime.engine)
    return ok({"templates": templates})
