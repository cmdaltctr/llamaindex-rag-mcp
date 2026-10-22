"""Operation descriptors and the catalogue registry.

Adding an operation needs one adapter and one ``catalogue.register()``
line. The catalogue never branches on operation names: lookup is by
``(operation_id, version)`` and every behaviour difference lives in the
descriptor or the adapter. The composition root builds the catalogue and
injects it; there is no module-level default catalogue.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adapters import OperationAdapter
from .levers import ALLOWED_LEVERS
from .ports import PortSpec

OperationId = Annotated[
    str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=128)
]


class EffectClass(StrEnum):
    """The strongest side effect an operation can have.

    ``PURE`` transforms inputs only. ``READ_ONLY`` reads sources or the
    store. ``MODEL_CALL`` calls an embedding, reranker or completion model.
    ``SOURCE_COMMIT`` performs a protected source replacement in a
    collection, and is limited to one destination per graph.
    """

    PURE = "pure"
    READ_ONLY = "read_only"
    MODEL_CALL = "model_call"
    SOURCE_COMMIT = "source_commit"


class BypassSpec(BaseModel):
    """How a disabled node passes a value through.

    The input and output ports must have the same kind; the value is
    forwarded unchanged and keeps its upstream type.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_port: str
    output_port: str


class OperationDescriptor(BaseModel):
    """The published contract of one operation version.

    Attributes:
        operation_id: Dotted identifier ``family.name``.
        version: Positive operation version.
        title: Short display name.
        family: Operation family, for example ``retrieve``.
        description: Help text for clients.
        parameters: Pydantic model with ``extra="forbid"``.
        inputs: Input ports.
        outputs: Output ports.
        capabilities: Host capabilities the operation needs, for example
            ``reranker``. Unavailable capabilities make it unavailable.
        effect: Strongest side effect.
        bypass: Pass-through used when the node is disabled, if allowed.
        collection_param: Parameter that names the bound collection.
        lever_params: Parameter name to lever path. ``None`` values
            inherit; other values are node overrides.
        option_params: Parameter name to host option-set name. The host
            reports which choices of such a parameter it cannot run.
        free_text_params: String parameters that are data (prompts), so
            the executable-text check does not apply to them.
        index_shaping: Whether the operation shapes stored chunks/vectors.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    operation_id: OperationId
    version: int = Field(ge=1)
    title: str
    family: str
    description: str = ""
    parameters: type[BaseModel]
    inputs: tuple[PortSpec, ...] = ()
    outputs: tuple[PortSpec, ...] = ()
    capabilities: tuple[str, ...] = ()
    effect: EffectClass
    bypass: BypassSpec | None = None
    collection_param: str | None = None
    lever_params: dict[str, str] = Field(default_factory=dict)
    option_params: dict[str, str] = Field(default_factory=dict)
    free_text_params: frozenset[str] = frozenset()
    index_shaping: bool = False

    @model_validator(mode="after")
    def _check_contract(self) -> OperationDescriptor:
        if self.parameters.model_config.get("extra") != "forbid":
            raise ValueError("parameters model must set extra='forbid' to reject unknown keys")
        for direction, ports in (("input", self.inputs), ("output", self.outputs)):
            names = [p.name for p in ports]
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate {direction} port names: {names}")
        fields = self.parameters.model_fields
        if self.collection_param is not None and self.collection_param not in fields:
            raise ValueError(f"collection_param {self.collection_param!r} is not a parameter")
        if self.effect is EffectClass.SOURCE_COMMIT and self.collection_param is None:
            raise ValueError("a source_commit operation must declare collection_param")
        for param, lever in self.lever_params.items():
            if param not in fields:
                raise ValueError(f"lever parameter {param!r} is not a parameter")
            if lever not in ALLOWED_LEVERS:
                raise ValueError(f"lever {lever!r} for {param!r} is not an allowed graph lever")
        for param in self.option_params:
            if param not in fields:
                raise ValueError(f"option parameter {param!r} is not a parameter")
        for name in self.free_text_params:
            if name not in fields:
                raise ValueError(f"free-text parameter {name!r} is not a parameter")
        if self.bypass is not None:
            self._check_bypass(self.bypass)
        return self

    def _check_bypass(self, bypass: BypassSpec) -> None:
        source = self.input_port(bypass.input_port)
        target = self.output_port(bypass.output_port)
        if source is None or target is None:
            raise ValueError("bypass must name a declared input port and output port")
        if source.type.kind is not target.type.kind:
            raise ValueError(
                f"bypass cannot forward '{source.type.kind.value}' into "
                f"'{target.type.kind.value}'; a bypass must keep the value kind"
            )

    @property
    def key(self) -> tuple[str, int]:
        """Return ``(operation_id, version)``."""
        return (self.operation_id, self.version)

    def input_port(self, name: str) -> PortSpec | None:
        """Return the input port called ``name``, if declared."""
        return next((p for p in self.inputs if p.name == name), None)

    def output_port(self, name: str) -> PortSpec | None:
        """Return the output port called ``name``, if declared."""
        return next((p for p in self.outputs if p.name == name), None)

    def to_schema(self) -> dict[str, Any]:
        """Return a JSON-safe description that clients can build controls from."""
        return {
            "operation_id": self.operation_id,
            "version": self.version,
            "title": self.title,
            "family": self.family,
            "description": self.description,
            "parameters": self.parameters.model_json_schema(),
            "inputs": [p.to_schema() for p in self.inputs],
            "outputs": [p.to_schema() for p in self.outputs],
            "capabilities": list(self.capabilities),
            "effect": self.effect.value,
            "bypass": self.bypass.model_dump() if self.bypass else None,
            "collection_param": self.collection_param,
            "lever_params": dict(self.lever_params),
            "option_params": dict(self.option_params),
            "free_text_params": sorted(self.free_text_params),
            "index_shaping": self.index_shaping,
        }


def _adapter_ref(adapter: Any) -> str:
    target = adapter if inspect.isfunction(adapter) or inspect.ismethod(adapter) else type(adapter)
    module = getattr(target, "__module__", "?")
    qualname = getattr(target, "__qualname__", repr(target))
    return f"{module}:{qualname}"


def _is_async_adapter(adapter: Any) -> bool:
    if inspect.iscoroutinefunction(adapter):
        return True
    return callable(adapter) and inspect.iscoroutinefunction(type(adapter).__call__)


@dataclass(frozen=True)
class HostOptionSet:
    """What the host knows about the choices of one setting.

    Attributes:
        inherited: Value a node inherits when its parameter is ``None``.
        unavailable: Choice to the reason the host cannot run it.
    """

    inherited: str | None = None
    unavailable: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RegisteredOperation:
    """A descriptor paired with its adapter."""

    descriptor: OperationDescriptor
    adapter: OperationAdapter
    adapter_ref: str


class OperationCatalogue:
    """Registry of operation descriptors and adapters."""

    def __init__(self) -> None:
        """Create an empty catalogue."""
        self._entries: dict[tuple[str, int], RegisteredOperation] = {}

    def register(self, descriptor: OperationDescriptor, adapter: OperationAdapter) -> None:
        """Register one operation version.

        Args:
            descriptor: The operation contract.
            adapter: Coroutine function or object with ``async __call__``.

        Raises:
            ValueError: If the same ``(operation_id, version)`` exists.
            TypeError: If ``adapter`` is not asynchronous.
        """
        if descriptor.key in self._entries:
            raise ValueError(
                f"Operation {descriptor.operation_id!r} version {descriptor.version} "
                "is already registered"
            )
        if not _is_async_adapter(adapter):
            raise TypeError(
                f"Adapter for {descriptor.operation_id!r} must be async "
                "(a coroutine function or an object with async __call__)"
            )
        self._entries[descriptor.key] = RegisteredOperation(
            descriptor, adapter, _adapter_ref(adapter)
        )

    def get(self, operation_id: str, version: int | None = None) -> RegisteredOperation | None:
        """Return a registered operation.

        Args:
            operation_id: Operation identifier.
            version: Exact version, or ``None`` for the highest registered.
        """
        if version is not None:
            return self._entries.get((operation_id, version))
        versions = [v for (op, v) in self._entries if op == operation_id]
        return self._entries[(operation_id, max(versions))] if versions else None

    def descriptors(self) -> tuple[OperationDescriptor, ...]:
        """Return every descriptor sorted by identifier and version."""
        return tuple(self._entries[key].descriptor for key in sorted(self._entries))

    def describe(
        self,
        capabilities: Mapping[str, str | None],
        options: Mapping[str, HostOptionSet] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the client catalogue with availability and reasons.

        Args:
            capabilities: Capability name to ``None`` (available) or a
                reason it is unavailable. Missing names are unavailable.
            options: Option-set name to what the host knows about that
                setting. Each operation reports the sets its
                ``option_params`` name; availability stays per operation.

        Returns:
            One JSON-safe entry per operation version.
        """
        listing = []
        for key in sorted(self._entries):
            entry = self._entries[key]
            reasons = capability_reasons(entry.descriptor, capabilities)
            schema = entry.descriptor.to_schema()
            unavailable, inherited = option_reports(entry.descriptor, options or {})
            schema.update(
                available=not reasons,
                unavailable_reasons=reasons,
                unavailable_options=unavailable,
                inherited_values=inherited,
                adapter_ref=entry.adapter_ref,
            )
            listing.append(schema)
        return listing


def capability_reasons(
    descriptor: OperationDescriptor, capabilities: Mapping[str, str | None]
) -> list[str]:
    """Return why the host cannot run ``descriptor``; empty when it can."""
    reasons = []
    for name in descriptor.capabilities:
        if name not in capabilities:
            reasons.append(f"Capability '{name}' is not provided by this host.")
        elif capabilities[name] is not None:
            reasons.append(f"Capability '{name}' is unavailable: {capabilities[name]}")
    return reasons


def option_reports(
    descriptor: OperationDescriptor, options: Mapping[str, HostOptionSet]
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Return ``(unavailable_options, inherited_values)`` for ``descriptor``.

    Both maps are empty when the operation has no option parameters or the
    host supplies no matching option set.
    """
    unavailable: dict[str, dict[str, str]] = {}
    inherited: dict[str, str] = {}
    for param, set_name in descriptor.option_params.items():
        option_set = options.get(set_name)
        if option_set is None:
            continue
        unavailable[param] = dict(option_set.unavailable)
        if option_set.inherited is not None:
            inherited[param] = option_set.inherited
    return unavailable, inherited
