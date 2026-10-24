"""Explicit, duplicate-checked registry for authored negative-bench mutations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Callable

from pydicom.dataset import Dataset

from ..model import GenerationError, MutationContext, MutationResult
from . import (
    codestream,
    codec_statement,
    color,
    conformance,
    deidentification,
    encoding,
    file_set,
    signatures,
    geometry,
    identity,
    object_set,
    pixel,
    relations,
    structure,
)
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


CORE_PROFILE_DOMAINS = (
    ("pixel", pixel.HANDLERS),
    ("geometry", geometry.HANDLERS),
    ("color", color.HANDLERS),
    ("identity", identity.HANDLERS),
    ("conformance", conformance.HANDLERS),
)
# The core-profile cohort's mutation inventory stays exact; the IOD structure and
# requirement-statement cohorts add their single-defect structure, relation, codestream and
# encoding mutations only to ALL_MUTATIONS, which generation dispatches through and which
# rejects any name that two domains would own.
MUTATION_REGISTRY: dict[str, MutationHandler] = build_registry(CORE_PROFILE_DOMAINS)
ALL_MUTATIONS: dict[str, MutationHandler] = build_registry(
    (
        *CORE_PROFILE_DOMAINS,
        ("structure", structure.HANDLERS),
        ("relations", relations.HANDLERS),
        ("codestream", codestream.HANDLERS),
        ("codec_statement", codec_statement.HANDLERS),
        ("encoding", encoding.HANDLERS),
        ("file_set", file_set.HANDLERS),
        ("deidentification", deidentification.HANDLERS),
        ("signatures", signatures.HANDLERS),
        ("object_set", object_set.HANDLERS),
    )
)

# Draft-v7 mutations are intentionally absent from the frozen v6 manifest.
V7_ONLY_MUTATIONS = frozenset(
    {"duplicate_sop_uid_different_pixels", "encrypted_attribute_edit",
     "file_set_edits", "iod_set_edits", "signature_mac_defect", "codec_statement_defect"}
)


def generate_case(
    case: dict, source: Path, input_dir: Path
) -> tuple[list[Path], list[dict]]:
    handler = ALL_MUTATIONS.get(case["mutation_name"])
    if handler is None:
        raise GenerationError(f"unsupported mutation: {case['mutation_name']}")
    if source.is_file():
        dataset = read_case_source(source)
    elif case["mutation_name"] == "iod_set_edits":
        dataset = Dataset()
    else:
        raise GenerationError(f"mutation source is not a file: {source}")
    context = MutationContext(
        case=case,
        source=source,
        input_dir=input_dir,
        dataset=dataset,
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
