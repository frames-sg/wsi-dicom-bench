"""Explicit, duplicate-checked registry for authored negative-bench mutations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Callable

from ..model import GenerationError, MutationContext, MutationResult
from . import codestream, color, conformance, encoding, geometry, identity, pixel, relations, structure
from .dicom import read_case_source, save


MutationHandler = Callable[[MutationContext], MutationResult | None]


class MutationRegistrationError(ValueError):
    """Two mutation domains attempted to own the same mutation name."""


def build_registry(
    domains: Iterable[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    owners: dict[str, str] = {}
    for domain, handlers in domains:
        for name, handler in handlers.items():
            if name in registry:
                raise MutationRegistrationError(
                    f"duplicate mutation {name!r} in {owners[name]!r} and {domain!r}"
                )
            registry[name] = handler
            owners[name] = domain
    return registry


CATALOG_V4_DOMAINS = (
    ("pixel", pixel.HANDLERS),
    ("geometry", geometry.HANDLERS),
    ("color", color.HANDLERS),
    ("identity", identity.HANDLERS),
    ("conformance", conformance.HANDLERS),
)
# The catalog-v4 mutation inventory stays exact; the v5 and v6 amendments add their
# single-defect IOD structure, relation, codestream and encoding mutations only to ALL_MUTATIONS,
# which generation dispatches through and which rejects any name that two domains would own.
MUTATION_REGISTRY: dict[str, MutationHandler] = build_registry(CATALOG_V4_DOMAINS)
ALL_MUTATIONS: dict[str, MutationHandler] = build_registry(
    (
        *CATALOG_V4_DOMAINS,
        ("structure", structure.HANDLERS),
        ("relations", relations.HANDLERS),
        ("codestream", codestream.HANDLERS),
        ("encoding", encoding.HANDLERS),
    )
)


def generate_case(
    case: dict, source: Path, input_dir: Path
) -> tuple[list[Path], list[dict]]:
    handler = ALL_MUTATIONS.get(case["mutation_name"])
    if handler is None:
        raise GenerationError(f"unsupported mutation: {case['mutation_name']}")
    context = MutationContext(
        case=case,
        source=source,
        input_dir=input_dir,
        dataset=read_case_source(source),
        changes=[
            {
                "kind": "harness_identity",
                "attribute": "SOPInstanceUID",
                "value": None,
            }
        ],
    )
    result = handler(context)
    if result is not None:
        return result.outputs, result.changes
    context.changes[0]["value"] = str(context.dataset.SOPInstanceUID)
    save(context.dataset, context.default_output)
    return [context.default_output], context.changes
