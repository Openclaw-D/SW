from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.contracts.workbench import DimensionSeriesRequest, DimensionSeriesResponse


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"generator value must be a mapping, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class GeneratedProjectBundle:
    catalog: dict[str, Any]
    workbench: dict[str, Any]
    dimension_series: tuple[dict[str, Any], ...] = ()


@runtime_checkable
class WorkbenchGeneratorAdapter(Protocol):
    @property
    def identity(self) -> str: ...

    def seed_bundles(self) -> Sequence[GeneratedProjectBundle]: ...

    def query_dimension_series(
        self, request: DimensionSeriesRequest
    ) -> DimensionSeriesResponse | Mapping[str, Any] | None: ...


class NullGeneratorAdapter:
    """Honest no-generator boundary used only until Back-3 lands.

    It never manufactures projects or metrics.  Because an empty run is not
    marked as seeded, a later restart immediately consumes Back-3 fixtures.
    """

    identity = "generator-unavailable"

    def seed_bundles(self) -> Sequence[GeneratedProjectBundle]:
        return ()

    def query_dimension_series(
        self, request: DimensionSeriesRequest
    ) -> DimensionSeriesResponse | None:
        return None


class ObjectGeneratorAdapter:
    def __init__(self, provider: Any, *, identity: str) -> None:
        self.provider = provider
        self.identity = identity

    def seed_bundles(self) -> Sequence[GeneratedProjectBundle]:
        raw: Any
        for name in (
            "seed_bundles",
            "build_seed_bundles",
            "generate_seed_bundles",
            "generate_projects",
            "build_projects",
        ):
            candidate = getattr(self.provider, name, None)
            if callable(candidate):
                raw = candidate()
                break
        else:
            raw = getattr(self.provider, "SEED_BUNDLES", None)
            if raw is None:
                raw = getattr(self.provider, "seed_projects", None)
            if raw is None:
                raise RuntimeError(
                    "Back-3 generator exists but exposes no supported seed bundle interface"
                )
        return tuple(self._bundle(item) for item in raw)

    @staticmethod
    def _bundle(value: Any) -> GeneratedProjectBundle:
        if isinstance(value, GeneratedProjectBundle):
            return value
        item = _mapping(value)
        catalog = item.get("catalog") or item.get("projectCatalog")
        workbench = item.get("workbench") or item.get("project")
        if catalog is None or workbench is None:
            raise RuntimeError("seed bundle requires catalog and workbench")
        series = item.get("dimensionSeries") or item.get("dimension_series") or ()
        return GeneratedProjectBundle(
            catalog=_mapping(catalog),
            workbench=_mapping(workbench),
            dimension_series=tuple(_mapping(entry) for entry in series),
        )

    def query_dimension_series(
        self, request: DimensionSeriesRequest
    ) -> DimensionSeriesResponse | Mapping[str, Any] | None:
        candidate = getattr(self.provider, "query_dimension_series", None)
        if not callable(candidate):
            return None
        return candidate(request)


def _call_factory(factory: Any, settings: Any) -> Any:
    signature = inspect.signature(factory)
    if len(signature.parameters) == 0:
        return factory()
    return factory(settings)


def discover_generator_adapter(settings: Any) -> WorkbenchGeneratorAdapter:
    """Discover the bounded Back-3 adapter without importing old JW Back.

    Back-3 may expose either a factory/provider object or module-level bundle
    functions.  Unsupported modules fail loudly instead of returning fake data.
    """

    modules = (
        "app.services.generation",
        "app.services.generation.generator",
        "app.services.generation.workbench",
        "app.services.generation.fixtures",
        "app.fixtures",
        "app.fixtures.workbench",
        "app.domain.generator",
    )
    loaded: list[Any] = []
    for module_name in modules:
        try:
            loaded.append(importlib.import_module(module_name))
        except ModuleNotFoundError as exc:
            if exc.name != module_name and not module_name.startswith(f"{exc.name}."):
                raise
    if not loaded:
        return NullGeneratorAdapter()
    for module in loaded:
        for factory_name in (
            "create_workbench_generator",
            "create_generator",
            "create_seed_provider",
        ):
            factory = getattr(module, factory_name, None)
            if callable(factory):
                provider = _call_factory(factory, settings)
                identity = getattr(provider, "identity", f"{module.__name__}:{factory_name}")
                return ObjectGeneratorAdapter(provider, identity=str(identity))
        if any(
            hasattr(module, name)
            for name in (
                "seed_bundles",
                "build_seed_bundles",
                "generate_seed_bundles",
                "generate_projects",
                "build_projects",
                "SEED_BUNDLES",
                "seed_projects",
            )
        ):
            version = getattr(module, "GENERATOR_VERSION", "v1")
            return ObjectGeneratorAdapter(
                module, identity=f"{module.__name__}:{version}:{getattr(settings, 'generator_seed', '')}"
            )
    concrete_generation_modules = [
        module
        for module in loaded
        if getattr(module, "__name__", "").startswith("app.services.generation")
        and getattr(module, "__file__", None)
    ]
    if concrete_generation_modules:
        names = ", ".join(module.__name__ for module in concrete_generation_modules)
        raise RuntimeError(
            "Back-3 generation modules are present but expose no supported "
            f"provider interface: {names}"
        )
    # With no concrete generation source, retain an explicit unavailable mode;
    # SeedService deliberately does not write a seed marker for this adapter.
    return NullGeneratorAdapter()
